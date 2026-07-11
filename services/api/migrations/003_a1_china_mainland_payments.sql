-- A1 China-mainland payment persistence.
-- Adds reference-only merchant configuration, CNY payment/refund records,
-- hash-only provider notification and bill evidence, reconciliation, and
-- append-only links into the billing ledger created by migration 002.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE billing_ledger_events
  DROP CONSTRAINT IF EXISTS billing_ledger_events_provider_check;
ALTER TABLE billing_ledger_events
  ADD CONSTRAINT billing_ledger_events_provider_check
  CHECK (provider IN ('stripe', 'wechat_pay', 'alipay', 'domestic_bank_card'));

CREATE OR REPLACE FUNCTION china_payment_public_metadata(p_metadata JSONB)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT
    COALESCE(p_metadata, '{}'::JSONB)::TEXT
      !~* '(sk_live_|sk_test_|rk_live_|rk_test_|whsec_|bearer[[:space:]]|-----begin[[:space:]][^-]*(private key|certificate)-----)'
    AND COALESCE(p_metadata, '{}'::JSONB)::TEXT
      !~* '"(raw_payload|payload|request_body|response_body|headers|authorization|secret|private_key|certificate|card_number|cardnumber|pan|cvc|cvv|cvv2|otp|one_time_password)"[[:space:]]*:';
$$;

CREATE OR REPLACE FUNCTION china_payment_reference_only(p_reference TEXT)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT
    p_reference ~ '^(vault|kms|provider-ref):[A-Za-z0-9._:/-]+$'
    AND p_reference !~ '[[:space:]]'
    AND p_reference !~* '(-----begin|sk_live_|sk_test_|rk_live_|rk_test_|whsec_|bearer[[:space:]])';
$$;

CREATE TABLE IF NOT EXISTS china_payment_merchant_applications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  provider TEXT NOT NULL CHECK (provider IN ('wechat_pay', 'alipay', 'domestic_bank_card')),
  mode TEXT NOT NULL DEFAULT 'test' CHECK (mode IN ('test', 'live')),
  merchant_ref TEXT NOT NULL,
  application_ref TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'suspended', 'rejected', 'closed')),
  application_fingerprint TEXT NOT NULL CHECK (application_fingerprint ~ '^[a-f0-9]{64}$'),
  submitted_at TIMESTAMPTZ,
  activated_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT china_payment_merchant_applications_scope_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT china_payment_merchant_applications_scope_provider_mode_key
    UNIQUE (organization_id, project_id, id, provider, mode),
  CONSTRAINT china_payment_merchant_applications_provider_ref_key
    UNIQUE (organization_id, project_id, provider, mode, merchant_ref, application_ref),
  CONSTRAINT china_payment_merchant_applications_fingerprint_key
    UNIQUE (organization_id, project_id, provider, mode, application_fingerprint),
  CONSTRAINT china_payment_merchant_applications_project_scope_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT china_payment_merchant_applications_metadata_safe
    CHECK (china_payment_public_metadata(metadata))
);

CREATE TABLE IF NOT EXISTS china_payment_config_refs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  merchant_application_id UUID NOT NULL,
  provider TEXT NOT NULL CHECK (provider IN ('wechat_pay', 'alipay', 'domestic_bank_card')),
  mode TEXT NOT NULL DEFAULT 'test' CHECK (mode IN ('test', 'live')),
  credential_ref TEXT NOT NULL,
  platform_key_ref TEXT NOT NULL,
  notification_verification_ref TEXT NOT NULL,
  config_fingerprint TEXT NOT NULL CHECK (config_fingerprint ~ '^[a-f0-9]{64}$'),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'rotating', 'disabled', 'retired')),
  effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
  effective_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT china_payment_config_refs_scope_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT china_payment_config_refs_application_scope_id_key
    UNIQUE (organization_id, project_id, merchant_application_id, id),
  CONSTRAINT china_payment_config_refs_order_scope_key
    UNIQUE (organization_id, project_id, merchant_application_id, provider, mode, id),
  CONSTRAINT china_payment_config_refs_fingerprint_key
    UNIQUE (organization_id, project_id, provider, mode, config_fingerprint),
  CONSTRAINT china_payment_config_refs_application_scope_fk
    FOREIGN KEY (organization_id, project_id, merchant_application_id, provider, mode)
    REFERENCES china_payment_merchant_applications(organization_id, project_id, id, provider, mode) ON DELETE CASCADE,
  CONSTRAINT china_payment_config_refs_credential_reference_only
    CHECK (china_payment_reference_only(credential_ref)),
  CONSTRAINT china_payment_config_refs_platform_key_reference_only
    CHECK (china_payment_reference_only(platform_key_ref)),
  CONSTRAINT china_payment_config_refs_notification_reference_only
    CHECK (china_payment_reference_only(notification_verification_ref)),
  CONSTRAINT china_payment_config_refs_effective_window
    CHECK (effective_until IS NULL OR effective_until > effective_from)
);

CREATE TABLE IF NOT EXISTS china_payment_acquirer_account_bindings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  merchant_application_id UUID NOT NULL,
  provider TEXT NOT NULL DEFAULT 'domestic_bank_card' CHECK (provider = 'domestic_bank_card'),
  mode TEXT NOT NULL DEFAULT 'test' CHECK (mode IN ('test', 'live')),
  acquirer TEXT NOT NULL,
  acquirer_account_ref TEXT NOT NULL,
  credential_ref TEXT NOT NULL,
  hosted_checkout_profile_ref TEXT,
  tokenization_profile_ref TEXT,
  binding_fingerprint TEXT NOT NULL CHECK (binding_fingerprint ~ '^[a-f0-9]{64}$'),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'rotating', 'disabled', 'retired')),
  capabilities TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT china_payment_acquirer_account_bindings_scope_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT china_payment_acquirer_account_bindings_order_scope_key
    UNIQUE (organization_id, project_id, merchant_application_id, provider, mode, id),
  CONSTRAINT china_payment_acquirer_account_bindings_account_key
    UNIQUE (organization_id, project_id, acquirer, mode, acquirer_account_ref),
  CONSTRAINT china_payment_acquirer_account_bindings_fingerprint_key
    UNIQUE (organization_id, project_id, acquirer, mode, binding_fingerprint),
  CONSTRAINT china_payment_acquirer_account_bindings_application_scope_fk
    FOREIGN KEY (organization_id, project_id, merchant_application_id, provider, mode)
    REFERENCES china_payment_merchant_applications(organization_id, project_id, id, provider, mode) ON DELETE CASCADE,
  CONSTRAINT china_payment_acquirer_account_bindings_account_reference_only
    CHECK (china_payment_reference_only(acquirer_account_ref)),
  CONSTRAINT china_payment_acquirer_bindings_credential_ref_only
    CHECK (china_payment_reference_only(credential_ref)),
  CONSTRAINT china_payment_acquirer_account_bindings_hosted_reference_only
    CHECK (hosted_checkout_profile_ref IS NULL OR china_payment_reference_only(hosted_checkout_profile_ref)),
  CONSTRAINT china_payment_acquirer_account_bindings_token_reference_only
    CHECK (tokenization_profile_ref IS NULL OR china_payment_reference_only(tokenization_profile_ref)),
  CONSTRAINT china_payment_acquirer_account_bindings_capabilities
    CHECK (
      capabilities <@ ARRAY['hosted', 'token', 'reference']::TEXT[]
      AND cardinality(capabilities) > 0
      AND ('hosted' <> ALL(capabilities) OR hosted_checkout_profile_ref IS NOT NULL)
      AND ('token' <> ALL(capabilities) OR tokenization_profile_ref IS NOT NULL)
      AND (hosted_checkout_profile_ref IS NULL OR 'hosted' = ANY(capabilities))
      AND (tokenization_profile_ref IS NULL OR 'token' = ANY(capabilities))
    ),
  CONSTRAINT china_payment_acquirer_account_bindings_metadata_safe
    CHECK (china_payment_public_metadata(metadata))
);

CREATE TABLE IF NOT EXISTS china_payment_orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  merchant_application_id UUID NOT NULL,
  config_ref_id UUID NOT NULL,
  provider TEXT NOT NULL CHECK (provider IN ('wechat_pay', 'alipay', 'domestic_bank_card')),
  mode TEXT NOT NULL DEFAULT 'test' CHECK (mode IN ('test', 'live')),
  acquirer_account_binding_id UUID,
  payment_contract TEXT,
  hosted_session_ref TEXT,
  payment_token_ref TEXT,
  card_reference TEXT,
  merchant_order_no TEXT NOT NULL,
  provider_order_ref TEXT,
  idempotency_key TEXT NOT NULL,
  request_fingerprint TEXT NOT NULL CHECK (request_fingerprint ~ '^[a-f0-9]{64}$'),
  amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
  currency TEXT NOT NULL DEFAULT 'cny' CHECK (currency = 'cny'),
  status TEXT NOT NULL DEFAULT 'created' CHECK (status IN ('created', 'pending', 'paid', 'closed', 'expired', 'failed')),
  subject TEXT NOT NULL,
  customer_ref TEXT,
  expires_at TIMESTAMPTZ,
  paid_at TIMESTAMPTZ,
  closed_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT china_payment_orders_scope_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT china_payment_orders_scope_provider_mode_key
    UNIQUE (organization_id, project_id, id, provider, mode),
  CONSTRAINT china_payment_orders_merchant_order_key
    UNIQUE (organization_id, project_id, provider, mode, merchant_order_no),
  CONSTRAINT china_payment_orders_idempotency_key
    UNIQUE (organization_id, project_id, idempotency_key),
  CONSTRAINT china_payment_orders_request_fingerprint_key
    UNIQUE (organization_id, project_id, provider, mode, request_fingerprint),
  CONSTRAINT china_payment_orders_application_scope_fk
    FOREIGN KEY (organization_id, project_id, merchant_application_id, provider, mode)
    REFERENCES china_payment_merchant_applications(organization_id, project_id, id, provider, mode) ON DELETE RESTRICT,
  CONSTRAINT china_payment_orders_config_application_scope_fk
    FOREIGN KEY (organization_id, project_id, merchant_application_id, provider, mode, config_ref_id)
    REFERENCES china_payment_config_refs(organization_id, project_id, merchant_application_id, provider, mode, id) ON DELETE RESTRICT,
  CONSTRAINT china_payment_orders_acquirer_binding_scope_fk
    FOREIGN KEY (organization_id, project_id, merchant_application_id, provider, mode, acquirer_account_binding_id)
    REFERENCES china_payment_acquirer_account_bindings(organization_id, project_id, merchant_application_id, provider, mode, id) ON DELETE RESTRICT,
  CONSTRAINT china_payment_orders_hosted_reference_only
    CHECK (hosted_session_ref IS NULL OR china_payment_reference_only(hosted_session_ref)),
  CONSTRAINT china_payment_orders_token_reference_only
    CHECK (payment_token_ref IS NULL OR china_payment_reference_only(payment_token_ref)),
  CONSTRAINT china_payment_orders_card_reference_only
    CHECK (card_reference IS NULL OR china_payment_reference_only(card_reference)),
  CONSTRAINT china_payment_orders_card_contract
    CHECK (
      (
        provider = 'domestic_bank_card'
        AND acquirer_account_binding_id IS NOT NULL
        AND payment_contract IN ('hosted', 'token', 'reference')
        AND num_nonnulls(hosted_session_ref, payment_token_ref, card_reference) = 1
        AND (payment_contract <> 'hosted' OR hosted_session_ref IS NOT NULL)
        AND (payment_contract <> 'token' OR payment_token_ref IS NOT NULL)
        AND (payment_contract <> 'reference' OR card_reference IS NOT NULL)
      )
      OR (
        provider IN ('wechat_pay', 'alipay')
        AND acquirer_account_binding_id IS NULL
        AND payment_contract IS NULL
        AND num_nonnulls(hosted_session_ref, payment_token_ref, card_reference) = 0
      )
    ),
  CONSTRAINT china_payment_orders_metadata_safe
    CHECK (china_payment_public_metadata(metadata)),
  CONSTRAINT china_payment_orders_state_times
    CHECK (
      (status <> 'paid' OR paid_at IS NOT NULL)
      AND (status NOT IN ('closed', 'expired') OR closed_at IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS china_payment_provider_notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  merchant_application_id UUID NOT NULL,
  order_id UUID,
  provider TEXT NOT NULL CHECK (provider IN ('wechat_pay', 'alipay', 'domestic_bank_card')),
  mode TEXT NOT NULL DEFAULT 'test' CHECK (mode IN ('test', 'live')),
  provider_notification_id TEXT NOT NULL,
  notification_type TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL CHECK (payload_sha256 ~ '^[a-f0-9]{64}$'),
  headers_sha256 TEXT CHECK (headers_sha256 IS NULL OR headers_sha256 ~ '^[a-f0-9]{64}$'),
  signature_verified BOOLEAN NOT NULL DEFAULT FALSE,
  occurred_at TIMESTAMPTZ,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  raw_payload_included BOOLEAN NOT NULL DEFAULT FALSE CHECK (raw_payload_included = FALSE),
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  CONSTRAINT china_payment_provider_notifications_scope_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT china_payment_provider_notifications_provider_id_key
    UNIQUE (organization_id, project_id, provider, mode, provider_notification_id),
  CONSTRAINT china_payment_provider_notifications_fingerprint_key
    UNIQUE (organization_id, project_id, provider, mode, payload_sha256),
  CONSTRAINT china_payment_provider_notifications_application_scope_fk
    FOREIGN KEY (organization_id, project_id, merchant_application_id, provider, mode)
    REFERENCES china_payment_merchant_applications(organization_id, project_id, id, provider, mode) ON DELETE RESTRICT,
  CONSTRAINT china_payment_provider_notifications_order_scope_fk
    FOREIGN KEY (organization_id, project_id, order_id, provider, mode)
    REFERENCES china_payment_orders(organization_id, project_id, id, provider, mode) ON DELETE RESTRICT,
  CONSTRAINT china_payment_provider_notifications_metadata_safe
    CHECK (china_payment_public_metadata(metadata))
);

CREATE TABLE IF NOT EXISTS china_payment_refunds (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  order_id UUID NOT NULL,
  provider TEXT NOT NULL CHECK (provider IN ('wechat_pay', 'alipay', 'domestic_bank_card')),
  mode TEXT NOT NULL DEFAULT 'test' CHECK (mode IN ('test', 'live')),
  merchant_refund_no TEXT NOT NULL,
  provider_refund_ref TEXT,
  idempotency_key TEXT NOT NULL,
  request_fingerprint TEXT NOT NULL CHECK (request_fingerprint ~ '^[a-f0-9]{64}$'),
  amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
  currency TEXT NOT NULL DEFAULT 'cny' CHECK (currency = 'cny'),
  reason_code TEXT,
  status TEXT NOT NULL DEFAULT 'created' CHECK (status IN ('created', 'processing', 'succeeded', 'failed', 'closed')),
  requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT china_payment_refunds_scope_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT china_payment_refunds_merchant_refund_key
    UNIQUE (organization_id, project_id, provider, mode, merchant_refund_no),
  CONSTRAINT china_payment_refunds_idempotency_key
    UNIQUE (organization_id, project_id, idempotency_key),
  CONSTRAINT china_payment_refunds_request_fingerprint_key
    UNIQUE (organization_id, project_id, provider, mode, request_fingerprint),
  CONSTRAINT china_payment_refunds_order_scope_fk
    FOREIGN KEY (organization_id, project_id, order_id, provider, mode)
    REFERENCES china_payment_orders(organization_id, project_id, id, provider, mode) ON DELETE RESTRICT,
  CONSTRAINT china_payment_refunds_metadata_safe
    CHECK (china_payment_public_metadata(metadata)),
  CONSTRAINT china_payment_refunds_state_times
    CHECK (status NOT IN ('succeeded', 'failed', 'closed') OR completed_at IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS china_payment_daily_bill_files (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  merchant_application_id UUID NOT NULL,
  provider TEXT NOT NULL CHECK (provider IN ('wechat_pay', 'alipay', 'domestic_bank_card')),
  mode TEXT NOT NULL DEFAULT 'test' CHECK (mode IN ('test', 'live')),
  bill_date DATE NOT NULL,
  provider_bill_ref TEXT NOT NULL,
  object_ref TEXT NOT NULL,
  file_sha256 TEXT NOT NULL CHECK (file_sha256 ~ '^[a-f0-9]{64}$'),
  line_count INTEGER NOT NULL DEFAULT 0 CHECK (line_count >= 0),
  status TEXT NOT NULL DEFAULT 'registered' CHECK (status IN ('registered', 'verified', 'parsed', 'reconciled', 'failed')),
  downloaded_at TIMESTAMPTZ,
  verified_at TIMESTAMPTZ,
  parsed_at TIMESTAMPTZ,
  reconciled_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT china_payment_daily_bill_files_scope_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT china_payment_daily_bill_files_provider_date_key
    UNIQUE (organization_id, project_id, provider, mode, merchant_application_id, bill_date),
  CONSTRAINT china_payment_daily_bill_files_provider_ref_key
    UNIQUE (organization_id, project_id, provider, mode, provider_bill_ref),
  CONSTRAINT china_payment_daily_bill_files_hash_key
    UNIQUE (organization_id, project_id, provider, mode, file_sha256),
  CONSTRAINT china_payment_daily_bill_files_application_scope_fk
    FOREIGN KEY (organization_id, project_id, merchant_application_id, provider, mode)
    REFERENCES china_payment_merchant_applications(organization_id, project_id, id, provider, mode) ON DELETE RESTRICT,
  CONSTRAINT china_payment_daily_bill_files_object_reference_only
    CHECK (object_ref ~ '^(s3|gs|oss|cos|artifact-ref):[A-Za-z0-9._:/-]+$' AND object_ref !~ '[[:space:]]'),
  CONSTRAINT china_payment_daily_bill_files_metadata_safe
    CHECK (china_payment_public_metadata(metadata))
);

CREATE TABLE IF NOT EXISTS china_payment_daily_bill_lines (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  bill_file_id UUID NOT NULL,
  order_id UUID,
  refund_id UUID,
  provider_line_ref TEXT NOT NULL,
  line_type TEXT NOT NULL CHECK (line_type IN ('payment', 'refund', 'fee', 'adjustment')),
  direction TEXT NOT NULL CHECK (direction IN ('credit', 'debit')),
  amount_minor BIGINT NOT NULL CHECK (amount_minor >= 0),
  fee_minor BIGINT NOT NULL DEFAULT 0 CHECK (fee_minor >= 0),
  currency TEXT NOT NULL DEFAULT 'cny' CHECK (currency = 'cny'),
  occurred_at TIMESTAMPTZ NOT NULL,
  line_fingerprint TEXT NOT NULL CHECK (line_fingerprint ~ '^[a-f0-9]{64}$'),
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT china_payment_daily_bill_lines_scope_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT china_payment_daily_bill_lines_provider_line_key
    UNIQUE (organization_id, project_id, bill_file_id, provider_line_ref),
  CONSTRAINT china_payment_daily_bill_lines_fingerprint_key
    UNIQUE (organization_id, project_id, bill_file_id, line_fingerprint),
  CONSTRAINT china_payment_daily_bill_lines_file_scope_fk
    FOREIGN KEY (organization_id, project_id, bill_file_id)
    REFERENCES china_payment_daily_bill_files(organization_id, project_id, id) ON DELETE RESTRICT,
  CONSTRAINT china_payment_daily_bill_lines_order_scope_fk
    FOREIGN KEY (organization_id, project_id, order_id)
    REFERENCES china_payment_orders(organization_id, project_id, id) ON DELETE RESTRICT,
  CONSTRAINT china_payment_daily_bill_lines_refund_scope_fk
    FOREIGN KEY (organization_id, project_id, refund_id)
    REFERENCES china_payment_refunds(organization_id, project_id, id) ON DELETE RESTRICT,
  CONSTRAINT china_payment_daily_bill_lines_subject_shape
    CHECK (
      (line_type = 'payment' AND order_id IS NOT NULL AND refund_id IS NULL)
      OR (line_type = 'refund' AND refund_id IS NOT NULL)
      OR (line_type IN ('fee', 'adjustment'))
    ),
  CONSTRAINT china_payment_daily_bill_lines_metadata_safe
    CHECK (china_payment_public_metadata(metadata))
);

CREATE TABLE IF NOT EXISTS china_payment_reconciliation_discrepancies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  bill_file_id UUID NOT NULL,
  bill_line_id UUID,
  order_id UUID,
  refund_id UUID,
  discrepancy_type TEXT NOT NULL CHECK (discrepancy_type IN ('missing_local', 'missing_provider', 'amount_mismatch', 'status_mismatch', 'duplicate', 'fee_mismatch')),
  expected_amount_minor BIGINT CHECK (expected_amount_minor IS NULL OR expected_amount_minor >= 0),
  observed_amount_minor BIGINT CHECK (observed_amount_minor IS NULL OR observed_amount_minor >= 0),
  difference_minor BIGINT NOT NULL DEFAULT 0,
  currency TEXT NOT NULL DEFAULT 'cny' CHECK (currency = 'cny'),
  evidence_fingerprint TEXT NOT NULL CHECK (evidence_fingerprint ~ '^[a-f0-9]{64}$'),
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'investigating', 'resolved', 'accepted')),
  resolution_code TEXT,
  resolution_evidence_sha256 TEXT CHECK (resolution_evidence_sha256 IS NULL OR resolution_evidence_sha256 ~ '^[a-f0-9]{64}$'),
  detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT china_payment_reconciliation_discrepancies_scope_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT china_payment_reconciliation_discrepancies_evidence_key
    UNIQUE (organization_id, project_id, bill_file_id, discrepancy_type, evidence_fingerprint),
  CONSTRAINT china_payment_reconciliation_discrepancies_file_scope_fk
    FOREIGN KEY (organization_id, project_id, bill_file_id)
    REFERENCES china_payment_daily_bill_files(organization_id, project_id, id) ON DELETE RESTRICT,
  CONSTRAINT china_payment_reconciliation_discrepancies_line_scope_fk
    FOREIGN KEY (organization_id, project_id, bill_line_id)
    REFERENCES china_payment_daily_bill_lines(organization_id, project_id, id) ON DELETE RESTRICT,
  CONSTRAINT china_payment_reconciliation_discrepancies_order_scope_fk
    FOREIGN KEY (organization_id, project_id, order_id)
    REFERENCES china_payment_orders(organization_id, project_id, id) ON DELETE RESTRICT,
  CONSTRAINT china_payment_reconciliation_discrepancies_refund_scope_fk
    FOREIGN KEY (organization_id, project_id, refund_id)
    REFERENCES china_payment_refunds(organization_id, project_id, id) ON DELETE RESTRICT,
  CONSTRAINT china_payment_reconciliation_discrepancies_resolution_shape
    CHECK (
      (status IN ('open', 'investigating') AND resolved_at IS NULL)
      OR (status IN ('resolved', 'accepted') AND resolved_at IS NOT NULL AND resolution_code IS NOT NULL)
    ),
  CONSTRAINT china_payment_reconciliation_discrepancies_difference_check
    CHECK (difference_minor = COALESCE(observed_amount_minor, 0) - COALESCE(expected_amount_minor, 0)),
  CONSTRAINT china_payment_reconciliation_discrepancies_metadata_safe
    CHECK (china_payment_public_metadata(metadata))
);

CREATE TABLE IF NOT EXISTS china_payment_ledger_links (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  billing_ledger_event_id UUID NOT NULL,
  link_type TEXT NOT NULL CHECK (link_type IN ('order', 'refund', 'notification', 'bill_line', 'discrepancy')),
  order_id UUID,
  refund_id UUID,
  notification_id UUID,
  bill_line_id UUID,
  discrepancy_id UUID,
  link_fingerprint TEXT NOT NULL CHECK (link_fingerprint ~ '^[a-f0-9]{64}$'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT china_payment_ledger_links_scope_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT china_payment_ledger_links_ledger_subject_key
    UNIQUE (organization_id, project_id, billing_ledger_event_id, link_type, link_fingerprint),
  CONSTRAINT china_payment_ledger_links_fingerprint_key
    UNIQUE (organization_id, project_id, link_fingerprint),
  CONSTRAINT china_payment_ledger_links_ledger_scope_fk
    FOREIGN KEY (organization_id, project_id, billing_ledger_event_id)
    REFERENCES billing_ledger_events(organization_id, project_id, id) ON DELETE RESTRICT,
  CONSTRAINT china_payment_ledger_links_order_scope_fk
    FOREIGN KEY (organization_id, project_id, order_id)
    REFERENCES china_payment_orders(organization_id, project_id, id) ON DELETE RESTRICT,
  CONSTRAINT china_payment_ledger_links_refund_scope_fk
    FOREIGN KEY (organization_id, project_id, refund_id)
    REFERENCES china_payment_refunds(organization_id, project_id, id) ON DELETE RESTRICT,
  CONSTRAINT china_payment_ledger_links_notification_scope_fk
    FOREIGN KEY (organization_id, project_id, notification_id)
    REFERENCES china_payment_provider_notifications(organization_id, project_id, id) ON DELETE RESTRICT,
  CONSTRAINT china_payment_ledger_links_bill_line_scope_fk
    FOREIGN KEY (organization_id, project_id, bill_line_id)
    REFERENCES china_payment_daily_bill_lines(organization_id, project_id, id) ON DELETE RESTRICT,
  CONSTRAINT china_payment_ledger_links_discrepancy_scope_fk
    FOREIGN KEY (organization_id, project_id, discrepancy_id)
    REFERENCES china_payment_reconciliation_discrepancies(organization_id, project_id, id) ON DELETE RESTRICT,
  CONSTRAINT china_payment_ledger_links_exactly_one_subject
    CHECK (num_nonnulls(order_id, refund_id, notification_id, bill_line_id, discrepancy_id) = 1),
  CONSTRAINT china_payment_ledger_links_subject_matches_type
    CHECK (
      (link_type = 'order' AND order_id IS NOT NULL)
      OR (link_type = 'refund' AND refund_id IS NOT NULL)
      OR (link_type = 'notification' AND notification_id IS NOT NULL)
      OR (link_type = 'bill_line' AND bill_line_id IS NOT NULL)
      OR (link_type = 'discrepancy' AND discrepancy_id IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS china_payment_mutation_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  table_name TEXT NOT NULL,
  row_id UUID NOT NULL,
  operation TEXT NOT NULL CHECK (operation IN ('insert', 'update', 'delete')),
  before_sha256 TEXT CHECK (before_sha256 IS NULL OR before_sha256 ~ '^[a-f0-9]{64}$'),
  after_sha256 TEXT CHECK (after_sha256 IS NULL OR after_sha256 ~ '^[a-f0-9]{64}$'),
  actor_ref TEXT,
  request_id TEXT,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT china_payment_mutation_events_scope_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT china_payment_mutation_events_fingerprint_key
    UNIQUE (organization_id, project_id, table_name, row_id, operation, occurred_at, before_sha256, after_sha256),
  CONSTRAINT china_payment_mutation_events_project_scope_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE RESTRICT,
  CONSTRAINT china_payment_mutation_events_evidence_shape
    CHECK (
      (operation = 'insert' AND before_sha256 IS NULL AND after_sha256 IS NOT NULL)
      OR (operation = 'update' AND before_sha256 IS NOT NULL AND after_sha256 IS NOT NULL)
      OR (operation = 'delete' AND before_sha256 IS NOT NULL AND after_sha256 IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_china_payment_merchant_applications_scope_status
  ON china_payment_merchant_applications(organization_id, project_id, provider, mode, status);
CREATE INDEX IF NOT EXISTS idx_china_payment_config_refs_scope_status
  ON china_payment_config_refs(organization_id, project_id, merchant_application_id, status, effective_from DESC);
CREATE INDEX IF NOT EXISTS idx_china_payment_acquirer_account_bindings_scope_status
  ON china_payment_acquirer_account_bindings(organization_id, project_id, acquirer, mode, status);
CREATE INDEX IF NOT EXISTS idx_china_payment_orders_scope_status_created
  ON china_payment_orders(organization_id, project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_china_payment_orders_provider_ref
  ON china_payment_orders(organization_id, project_id, provider, mode, provider_order_ref)
  WHERE provider_order_ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_china_payment_provider_notifications_scope_received
  ON china_payment_provider_notifications(organization_id, project_id, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_china_payment_provider_notifications_order
  ON china_payment_provider_notifications(organization_id, project_id, order_id, received_at DESC)
  WHERE order_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_china_payment_refunds_scope_status_created
  ON china_payment_refunds(organization_id, project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_china_payment_refunds_order
  ON china_payment_refunds(organization_id, project_id, order_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_china_payment_daily_bill_files_scope_date
  ON china_payment_daily_bill_files(organization_id, project_id, provider, mode, bill_date DESC);
CREATE INDEX IF NOT EXISTS idx_china_payment_daily_bill_lines_file_occurred
  ON china_payment_daily_bill_lines(organization_id, project_id, bill_file_id, occurred_at, id);
CREATE INDEX IF NOT EXISTS idx_china_payment_reconciliation_discrepancies_scope_status
  ON china_payment_reconciliation_discrepancies(organization_id, project_id, status, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_china_payment_ledger_links_ledger
  ON china_payment_ledger_links(organization_id, project_id, billing_ledger_event_id, created_at);
CREATE INDEX IF NOT EXISTS idx_china_payment_mutation_events_row
  ON china_payment_mutation_events(organization_id, project_id, table_name, row_id, occurred_at DESC);

ALTER TABLE china_payment_merchant_applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE china_payment_config_refs ENABLE ROW LEVEL SECURITY;
ALTER TABLE china_payment_acquirer_account_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE china_payment_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE china_payment_provider_notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE china_payment_refunds ENABLE ROW LEVEL SECURITY;
ALTER TABLE china_payment_daily_bill_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE china_payment_daily_bill_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE china_payment_reconciliation_discrepancies ENABLE ROW LEVEL SECURITY;
ALTER TABLE china_payment_ledger_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE china_payment_mutation_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE china_payment_merchant_applications FORCE ROW LEVEL SECURITY;
ALTER TABLE china_payment_config_refs FORCE ROW LEVEL SECURITY;
ALTER TABLE china_payment_acquirer_account_bindings FORCE ROW LEVEL SECURITY;
ALTER TABLE china_payment_orders FORCE ROW LEVEL SECURITY;
ALTER TABLE china_payment_provider_notifications FORCE ROW LEVEL SECURITY;
ALTER TABLE china_payment_refunds FORCE ROW LEVEL SECURITY;
ALTER TABLE china_payment_daily_bill_files FORCE ROW LEVEL SECURITY;
ALTER TABLE china_payment_daily_bill_lines FORCE ROW LEVEL SECURITY;
ALTER TABLE china_payment_reconciliation_discrepancies FORCE ROW LEVEL SECURITY;
ALTER TABLE china_payment_ledger_links FORCE ROW LEVEL SECURITY;
ALTER TABLE china_payment_mutation_events FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS china_payment_merchant_applications_organization_isolation ON china_payment_merchant_applications;
DROP POLICY IF EXISTS china_payment_config_refs_organization_isolation ON china_payment_config_refs;
DROP POLICY IF EXISTS china_payment_acquirer_account_bindings_organization_isolation ON china_payment_acquirer_account_bindings;
DROP POLICY IF EXISTS china_payment_orders_organization_isolation ON china_payment_orders;
DROP POLICY IF EXISTS china_payment_provider_notifications_organization_isolation ON china_payment_provider_notifications;
DROP POLICY IF EXISTS china_payment_refunds_organization_isolation ON china_payment_refunds;
DROP POLICY IF EXISTS china_payment_daily_bill_files_organization_isolation ON china_payment_daily_bill_files;
DROP POLICY IF EXISTS china_payment_daily_bill_lines_organization_isolation ON china_payment_daily_bill_lines;
DROP POLICY IF EXISTS china_payment_recon_discrepancies_org_isolation ON china_payment_reconciliation_discrepancies;
DROP POLICY IF EXISTS china_payment_ledger_links_organization_isolation ON china_payment_ledger_links;
DROP POLICY IF EXISTS china_payment_mutation_events_organization_isolation ON china_payment_mutation_events;

CREATE POLICY china_payment_merchant_applications_organization_isolation ON china_payment_merchant_applications
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());
CREATE POLICY china_payment_config_refs_organization_isolation ON china_payment_config_refs
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());
CREATE POLICY china_payment_acquirer_account_bindings_organization_isolation ON china_payment_acquirer_account_bindings
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());
CREATE POLICY china_payment_orders_organization_isolation ON china_payment_orders
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());
CREATE POLICY china_payment_provider_notifications_organization_isolation ON china_payment_provider_notifications
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());
CREATE POLICY china_payment_refunds_organization_isolation ON china_payment_refunds
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());
CREATE POLICY china_payment_daily_bill_files_organization_isolation ON china_payment_daily_bill_files
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());
CREATE POLICY china_payment_daily_bill_lines_organization_isolation ON china_payment_daily_bill_lines
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());
CREATE POLICY china_payment_recon_discrepancies_org_isolation ON china_payment_reconciliation_discrepancies
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());
CREATE POLICY china_payment_ledger_links_organization_isolation ON china_payment_ledger_links
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());
CREATE POLICY china_payment_mutation_events_organization_isolation ON china_payment_mutation_events
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE OR REPLACE FUNCTION china_payment_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION china_payment_record_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  target_row JSONB;
  target_organization_id UUID;
  target_project_id UUID;
  target_row_id UUID;
  before_digest TEXT;
  after_digest TEXT;
BEGIN
  target_row := CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
  target_organization_id := (target_row ->> 'organization_id')::UUID;
  target_project_id := (target_row ->> 'project_id')::UUID;
  target_row_id := (target_row ->> 'id')::UUID;
  before_digest := CASE
    WHEN TG_OP IN ('UPDATE', 'DELETE') THEN encode(digest(to_jsonb(OLD)::TEXT, 'sha256'), 'hex')
    ELSE NULL
  END;
  after_digest := CASE
    WHEN TG_OP IN ('INSERT', 'UPDATE') THEN encode(digest(to_jsonb(NEW)::TEXT, 'sha256'), 'hex')
    ELSE NULL
  END;

  INSERT INTO china_payment_mutation_events (
    organization_id,
    project_id,
    table_name,
    row_id,
    operation,
    before_sha256,
    after_sha256,
    actor_ref,
    request_id
  ) VALUES (
    target_organization_id,
    target_project_id,
    TG_TABLE_NAME,
    target_row_id,
    lower(TG_OP),
    before_digest,
    after_digest,
    NULLIF(current_setting('app.a1_actor_ref', TRUE), ''),
    NULLIF(current_setting('app.a1_request_id', TRUE), '')
  );

  RETURN COALESCE(NEW, OLD);
END;
$$;

CREATE OR REPLACE FUNCTION china_payment_reject_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION '% is append-only; % is not permitted', TG_TABLE_NAME, TG_OP
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION china_payment_validate_refund()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  order_amount_minor BIGINT;
  existing_refund_minor BIGINT;
BEGIN
  SELECT amount_minor
    INTO order_amount_minor
    FROM china_payment_orders
   WHERE organization_id = NEW.organization_id
     AND project_id = NEW.project_id
     AND id = NEW.order_id
     AND provider = NEW.provider
     AND mode = NEW.mode
     AND currency = NEW.currency
   FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'refund order must exist in the same tenant, project, provider, mode, and currency';
  END IF;

  SELECT COALESCE(SUM(amount_minor), 0)
    INTO existing_refund_minor
    FROM china_payment_refunds
   WHERE organization_id = NEW.organization_id
     AND project_id = NEW.project_id
     AND order_id = NEW.order_id
     AND status NOT IN ('failed', 'closed')
     AND id IS DISTINCT FROM NEW.id;

  IF existing_refund_minor + NEW.amount_minor > order_amount_minor THEN
    RAISE EXCEPTION 'aggregate active refund amount exceeds payment order amount';
  END IF;

  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION china_payment_validate_ledger_link()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  ledger_provider TEXT;
  ledger_mode TEXT;
  subject_provider TEXT;
  subject_mode TEXT;
BEGIN
  SELECT provider, mode
    INTO ledger_provider, ledger_mode
    FROM billing_ledger_events
   WHERE organization_id = NEW.organization_id
     AND project_id = NEW.project_id
     AND id = NEW.billing_ledger_event_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'ledger event must exist in the same tenant and project';
  END IF;

  CASE NEW.link_type
    WHEN 'order' THEN
      SELECT provider, mode
        INTO subject_provider, subject_mode
        FROM china_payment_orders
       WHERE organization_id = NEW.organization_id
         AND project_id = NEW.project_id
         AND id = NEW.order_id;
    WHEN 'refund' THEN
      SELECT provider, mode
        INTO subject_provider, subject_mode
        FROM china_payment_refunds
       WHERE organization_id = NEW.organization_id
         AND project_id = NEW.project_id
         AND id = NEW.refund_id;
    WHEN 'notification' THEN
      SELECT provider, mode
        INTO subject_provider, subject_mode
        FROM china_payment_provider_notifications
       WHERE organization_id = NEW.organization_id
         AND project_id = NEW.project_id
         AND id = NEW.notification_id;
    WHEN 'bill_line' THEN
      SELECT bill_file.provider, bill_file.mode
        INTO subject_provider, subject_mode
        FROM china_payment_daily_bill_lines AS bill_line
        JOIN china_payment_daily_bill_files AS bill_file
          ON bill_file.organization_id = bill_line.organization_id
         AND bill_file.project_id = bill_line.project_id
         AND bill_file.id = bill_line.bill_file_id
       WHERE bill_line.organization_id = NEW.organization_id
         AND bill_line.project_id = NEW.project_id
         AND bill_line.id = NEW.bill_line_id;
    WHEN 'discrepancy' THEN
      SELECT bill_file.provider, bill_file.mode
        INTO subject_provider, subject_mode
        FROM china_payment_reconciliation_discrepancies AS discrepancy
        JOIN china_payment_daily_bill_files AS bill_file
          ON bill_file.organization_id = discrepancy.organization_id
         AND bill_file.project_id = discrepancy.project_id
         AND bill_file.id = discrepancy.bill_file_id
       WHERE discrepancy.organization_id = NEW.organization_id
         AND discrepancy.project_id = NEW.project_id
         AND discrepancy.id = NEW.discrepancy_id;
  END CASE;

  IF subject_provider IS NULL OR subject_mode IS NULL THEN
    RAISE EXCEPTION 'ledger link subject must exist in the same tenant and project';
  END IF;

  IF subject_provider <> ledger_provider OR subject_mode <> ledger_mode THEN
    RAISE EXCEPTION 'ledger event provider and mode must match the linked payment subject';
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS china_payment_merchant_applications_set_updated_at ON china_payment_merchant_applications;
CREATE TRIGGER china_payment_merchant_applications_set_updated_at
BEFORE UPDATE ON china_payment_merchant_applications
FOR EACH ROW EXECUTE FUNCTION china_payment_set_updated_at();
DROP TRIGGER IF EXISTS china_payment_config_refs_set_updated_at ON china_payment_config_refs;
CREATE TRIGGER china_payment_config_refs_set_updated_at
BEFORE UPDATE ON china_payment_config_refs
FOR EACH ROW EXECUTE FUNCTION china_payment_set_updated_at();
DROP TRIGGER IF EXISTS china_payment_acquirer_account_bindings_set_updated_at ON china_payment_acquirer_account_bindings;
CREATE TRIGGER china_payment_acquirer_account_bindings_set_updated_at
BEFORE UPDATE ON china_payment_acquirer_account_bindings
FOR EACH ROW EXECUTE FUNCTION china_payment_set_updated_at();
DROP TRIGGER IF EXISTS china_payment_orders_set_updated_at ON china_payment_orders;
CREATE TRIGGER china_payment_orders_set_updated_at
BEFORE UPDATE ON china_payment_orders
FOR EACH ROW EXECUTE FUNCTION china_payment_set_updated_at();
DROP TRIGGER IF EXISTS china_payment_refunds_set_updated_at ON china_payment_refunds;
CREATE TRIGGER china_payment_refunds_set_updated_at
BEFORE UPDATE ON china_payment_refunds
FOR EACH ROW EXECUTE FUNCTION china_payment_set_updated_at();
DROP TRIGGER IF EXISTS china_payment_refunds_validate_amount ON china_payment_refunds;
CREATE TRIGGER china_payment_refunds_validate_amount
BEFORE INSERT OR UPDATE OF order_id, provider, mode, amount_minor, currency, status ON china_payment_refunds
FOR EACH ROW EXECUTE FUNCTION china_payment_validate_refund();
DROP TRIGGER IF EXISTS china_payment_daily_bill_files_set_updated_at ON china_payment_daily_bill_files;
CREATE TRIGGER china_payment_daily_bill_files_set_updated_at
BEFORE UPDATE ON china_payment_daily_bill_files
FOR EACH ROW EXECUTE FUNCTION china_payment_set_updated_at();
DROP TRIGGER IF EXISTS china_payment_reconciliation_discrepancies_set_updated_at ON china_payment_reconciliation_discrepancies;
CREATE TRIGGER china_payment_reconciliation_discrepancies_set_updated_at
BEFORE UPDATE ON china_payment_reconciliation_discrepancies
FOR EACH ROW EXECUTE FUNCTION china_payment_set_updated_at();

DROP TRIGGER IF EXISTS china_payment_merchant_applications_audit ON china_payment_merchant_applications;
CREATE TRIGGER china_payment_merchant_applications_audit
AFTER INSERT OR UPDATE OR DELETE ON china_payment_merchant_applications
FOR EACH ROW EXECUTE FUNCTION china_payment_record_mutation();
DROP TRIGGER IF EXISTS china_payment_config_refs_audit ON china_payment_config_refs;
CREATE TRIGGER china_payment_config_refs_audit
AFTER INSERT OR UPDATE OR DELETE ON china_payment_config_refs
FOR EACH ROW EXECUTE FUNCTION china_payment_record_mutation();
DROP TRIGGER IF EXISTS china_payment_acquirer_account_bindings_audit ON china_payment_acquirer_account_bindings;
CREATE TRIGGER china_payment_acquirer_account_bindings_audit
AFTER INSERT OR UPDATE OR DELETE ON china_payment_acquirer_account_bindings
FOR EACH ROW EXECUTE FUNCTION china_payment_record_mutation();
DROP TRIGGER IF EXISTS china_payment_orders_audit ON china_payment_orders;
CREATE TRIGGER china_payment_orders_audit
AFTER INSERT OR UPDATE OR DELETE ON china_payment_orders
FOR EACH ROW EXECUTE FUNCTION china_payment_record_mutation();
DROP TRIGGER IF EXISTS china_payment_refunds_audit ON china_payment_refunds;
CREATE TRIGGER china_payment_refunds_audit
AFTER INSERT OR UPDATE OR DELETE ON china_payment_refunds
FOR EACH ROW EXECUTE FUNCTION china_payment_record_mutation();
DROP TRIGGER IF EXISTS china_payment_daily_bill_files_audit ON china_payment_daily_bill_files;
CREATE TRIGGER china_payment_daily_bill_files_audit
AFTER INSERT OR UPDATE OR DELETE ON china_payment_daily_bill_files
FOR EACH ROW EXECUTE FUNCTION china_payment_record_mutation();
DROP TRIGGER IF EXISTS china_payment_reconciliation_discrepancies_audit ON china_payment_reconciliation_discrepancies;
CREATE TRIGGER china_payment_reconciliation_discrepancies_audit
AFTER INSERT OR UPDATE OR DELETE ON china_payment_reconciliation_discrepancies
FOR EACH ROW EXECUTE FUNCTION china_payment_record_mutation();

DROP TRIGGER IF EXISTS china_payment_provider_notifications_append_only ON china_payment_provider_notifications;
CREATE TRIGGER china_payment_provider_notifications_append_only
BEFORE UPDATE OR DELETE ON china_payment_provider_notifications
FOR EACH ROW EXECUTE FUNCTION china_payment_reject_mutation();
DROP TRIGGER IF EXISTS china_payment_daily_bill_lines_append_only ON china_payment_daily_bill_lines;
CREATE TRIGGER china_payment_daily_bill_lines_append_only
BEFORE UPDATE OR DELETE ON china_payment_daily_bill_lines
FOR EACH ROW EXECUTE FUNCTION china_payment_reject_mutation();
DROP TRIGGER IF EXISTS china_payment_ledger_links_append_only ON china_payment_ledger_links;
CREATE TRIGGER china_payment_ledger_links_append_only
BEFORE UPDATE OR DELETE ON china_payment_ledger_links
FOR EACH ROW EXECUTE FUNCTION china_payment_reject_mutation();
DROP TRIGGER IF EXISTS china_payment_ledger_links_validate_rail ON china_payment_ledger_links;
CREATE TRIGGER china_payment_ledger_links_validate_rail
BEFORE INSERT ON china_payment_ledger_links
FOR EACH ROW EXECUTE FUNCTION china_payment_validate_ledger_link();
DROP TRIGGER IF EXISTS china_payment_mutation_events_append_only ON china_payment_mutation_events;
CREATE TRIGGER china_payment_mutation_events_append_only
BEFORE UPDATE OR DELETE ON china_payment_mutation_events
FOR EACH ROW EXECUTE FUNCTION china_payment_reject_mutation();

COMMIT;
