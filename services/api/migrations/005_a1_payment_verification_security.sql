-- A1 payment verification security.
-- Adds recursive public-metadata admission, immutable verification evidence,
-- fail-closed provider-authoritative status transitions, and project-scoped RLS.

BEGIN;

CREATE OR REPLACE FUNCTION china_payment_public_metadata(p_metadata JSONB)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  item RECORD;
  normalized_key TEXT;
  scalar_value TEXT;
BEGIN
  IF p_metadata IS NULL THEN
    RETURN TRUE;
  END IF;

  CASE jsonb_typeof(p_metadata)
    WHEN 'object' THEN
      FOR item IN SELECT key, value FROM jsonb_each(p_metadata)
      LOOP
        normalized_key := lower(regexp_replace(item.key, '[^a-zA-Z0-9]', '', 'g'));
        IF normalized_key = ANY (ARRAY[
          'rawpayload', 'providerpayload', 'payloadbody', 'requestbody',
          'responsebody', 'rawrequest', 'rawresponse', 'headers',
          'requestheaders', 'responseheaders', 'authorization',
          'proxyauthorization', 'cookie', 'setcookie', 'secret',
          'clientsecret', 'apisecret', 'webhooksecret', 'signingsecret',
          'privatekey', 'merchantprivatekey', 'platformprivatekey',
          'certificate', 'certificatepem', 'certpem', 'keypem',
          'cardnumber', 'cardno', 'cardnum', 'accountnumber',
          'primaryaccountnumber', 'pan', 'cvc', 'cvv', 'cvv2', 'cid',
          'securitycode', 'expiry', 'expirydate', 'expirationdate',
          'expmonth', 'expyear', 'pin', 'pinblock', 'track1', 'track2',
          'trackdata', 'magstripe', 'cryptogram', 'arqc', 'otp',
          'onetimepassword', 'smsverificationcode', 'bankcardnumber',
          'debitcardnumber', 'creditcardnumber'
        ]) THEN
          RETURN FALSE;
        END IF;
        IF NOT china_payment_public_metadata(item.value) THEN
          RETURN FALSE;
        END IF;
      END LOOP;
      RETURN TRUE;
    WHEN 'array' THEN
      FOR item IN SELECT value FROM jsonb_array_elements(p_metadata)
      LOOP
        IF NOT china_payment_public_metadata(item.value) THEN
          RETURN FALSE;
        END IF;
      END LOOP;
      RETURN TRUE;
    WHEN 'string' THEN
      scalar_value := p_metadata #>> '{}';
      RETURN scalar_value !~* (
        '(^|[^A-Za-z0-9])(?:sk_live_|sk_test_|rk_live_|rk_test_|whsec_)'
        || '|bearer[[:space:]]+[A-Za-z0-9._~+/-]+'
        || '|-----begin[[:space:]][^-]*(?:private key|certificate)-----'
      );
    ELSE
      RETURN TRUE;
  END CASE;
END;
$$;

ALTER TABLE billing_accounts
  DROP CONSTRAINT IF EXISTS billing_accounts_no_raw_secret;
ALTER TABLE billing_accounts
  ADD CONSTRAINT billing_accounts_metadata_safe
  CHECK (china_payment_public_metadata(metadata)) NOT VALID;

ALTER TABLE billing_provider_events
  DROP CONSTRAINT IF EXISTS billing_provider_events_no_raw_secret;
ALTER TABLE billing_provider_events
  ADD CONSTRAINT billing_provider_events_metadata_safe
  CHECK (china_payment_public_metadata(metadata)) NOT VALID;

ALTER TABLE billing_ledger_events
  DROP CONSTRAINT IF EXISTS billing_ledger_events_no_raw_secret;
ALTER TABLE billing_ledger_events
  ADD CONSTRAINT billing_ledger_events_metadata_safe
  CHECK (china_payment_public_metadata(metadata)) NOT VALID;

CREATE OR REPLACE FUNCTION a1_current_project_id()
RETURNS UUID
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('app.a1_project_id', TRUE), '')::UUID;
$$;

CREATE OR REPLACE FUNCTION a1_role_is_nobypassrls(p_role NAME DEFAULT current_user)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
  SELECT COALESCE(
    (
      SELECT NOT rolbypassrls AND NOT rolsuper
        FROM pg_roles
       WHERE rolname = p_role
    ),
    FALSE
  );
$$;

CREATE OR REPLACE FUNCTION a1_assert_role_nobypassrls(p_role NAME DEFAULT current_user)
RETURNS VOID
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF NOT a1_role_is_nobypassrls(p_role) THEN
    RAISE EXCEPTION 'payment runtime role % must be NOSUPERUSER NOBYPASSRLS', p_role
      USING ERRCODE = '42501';
  END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS china_payment_verification_artifacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  merchant_application_id UUID NOT NULL,
  provider TEXT NOT NULL CHECK (provider IN ('wechat_pay', 'alipay', 'domestic_bank_card')),
  mode TEXT NOT NULL DEFAULT 'test' CHECK (mode IN ('test', 'live')),
  provider_notification_id TEXT NOT NULL,
  notification_type TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL CHECK (payload_sha256 ~ '^[a-f0-9]{64}$'),
  headers_sha256 TEXT CHECK (headers_sha256 IS NULL OR headers_sha256 ~ '^[a-f0-9]{64}$'),
  verifier_kind TEXT NOT NULL CHECK (verifier_kind IN (
    'wechat_pay_v3', 'alipay_public_key', 'domestic_acquirer_signature'
  )),
  verifier_version TEXT NOT NULL,
  verification_key_ref TEXT NOT NULL,
  verification_key_fingerprint TEXT NOT NULL
    CHECK (verification_key_fingerprint ~ '^[a-f0-9]{64}$'),
  signature_sha256 TEXT NOT NULL CHECK (signature_sha256 ~ '^[a-f0-9]{64}$'),
  result TEXT NOT NULL DEFAULT 'verified' CHECK (result = 'verified'),
  reason_codes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  target_kind TEXT NOT NULL CHECK (target_kind IN ('order', 'refund')),
  target_id UUID NOT NULL,
  authorized_status TEXT NOT NULL,
  artifact_sha256 TEXT NOT NULL CHECK (artifact_sha256 ~ '^[a-f0-9]{64}$'),
  verified_at TIMESTAMPTZ NOT NULL,
  provider_occurred_at TIMESTAMPTZ,
  fresh_until TIMESTAMPTZ NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT china_payment_verification_artifacts_scope_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT china_payment_verification_artifacts_notification_key
    UNIQUE (
      organization_id, project_id, merchant_application_id, provider, mode,
      provider_notification_id, payload_sha256, id
    ),
  CONSTRAINT china_payment_verification_artifacts_replay_key
    UNIQUE (organization_id, project_id, provider, mode, provider_notification_id),
  CONSTRAINT china_payment_verification_artifacts_target_status_key
    UNIQUE (organization_id, project_id, target_kind, target_id, authorized_status),
  CONSTRAINT china_payment_verification_artifacts_digest_key
    UNIQUE (organization_id, project_id, artifact_sha256),
  CONSTRAINT china_payment_verification_artifacts_application_scope_fk
    FOREIGN KEY (organization_id, project_id, merchant_application_id, provider, mode)
    REFERENCES china_payment_merchant_applications(
      organization_id, project_id, id, provider, mode
    ) ON DELETE RESTRICT,
  CONSTRAINT china_payment_verification_artifacts_key_reference_only
    CHECK (china_payment_reference_only(verification_key_ref)),
  CONSTRAINT china_payment_verification_artifacts_fresh_window
    CHECK (
      verified_at <= created_at + INTERVAL '5 minutes'
      AND fresh_until > verified_at
      AND fresh_until <= verified_at + INTERVAL '24 hours'
    ),
  CONSTRAINT china_payment_verification_artifacts_reason_codes_safe
    CHECK (
      cardinality(reason_codes) <= 32
      AND array_position(reason_codes, NULL) IS NULL
      AND reason_codes::TEXT !~* '(secret|signature|payload|header|certificate|private.?key|card|pan|cvv|otp)'
    ),
  CONSTRAINT china_payment_verification_artifacts_target_status
    CHECK (
      (target_kind = 'order' AND authorized_status IN ('paid', 'closed', 'expired', 'failed'))
      OR
      (target_kind = 'refund' AND authorized_status IN ('succeeded', 'failed', 'closed'))
    ),
  CONSTRAINT china_payment_verification_artifacts_metadata_safe
    CHECK (china_payment_public_metadata(metadata))
);

ALTER TABLE china_payment_provider_notifications
  ADD COLUMN IF NOT EXISTS verification_artifact_id UUID;

ALTER TABLE china_payment_provider_notifications
  DROP CONSTRAINT IF EXISTS china_payment_provider_notifications_artifact_scope_fk;
ALTER TABLE china_payment_provider_notifications
  ADD CONSTRAINT china_payment_provider_notifications_artifact_scope_fk
  FOREIGN KEY (
    organization_id, project_id, merchant_application_id, provider, mode,
    provider_notification_id, payload_sha256, verification_artifact_id
  )
  REFERENCES china_payment_verification_artifacts(
    organization_id, project_id, merchant_application_id, provider, mode,
    provider_notification_id, payload_sha256, id
  ) ON DELETE RESTRICT NOT VALID;

CREATE UNIQUE INDEX IF NOT EXISTS idx_china_payment_notifications_artifact
  ON china_payment_provider_notifications(verification_artifact_id)
  WHERE verification_artifact_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_china_payment_verification_scope_created
  ON china_payment_verification_artifacts(
    organization_id, project_id, provider, mode, created_at DESC
  );
CREATE INDEX IF NOT EXISTS idx_china_payment_verification_target
  ON china_payment_verification_artifacts(
    organization_id, project_id, target_kind, target_id, authorized_status
  );
CREATE INDEX IF NOT EXISTS idx_china_payment_verification_fresh
  ON china_payment_verification_artifacts(fresh_until);

ALTER TABLE china_payment_verification_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE china_payment_verification_artifacts FORCE ROW LEVEL SECURITY;

REVOKE UPDATE, DELETE, TRUNCATE ON china_payment_verification_artifacts FROM PUBLIC;

CREATE OR REPLACE FUNCTION china_payment_reject_verification_artifact_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'payment verification artifacts are append-only'
    USING ERRCODE = '55000';
END;
$$;

DROP TRIGGER IF EXISTS china_payment_verification_artifacts_append_only
  ON china_payment_verification_artifacts;
CREATE TRIGGER china_payment_verification_artifacts_append_only
BEFORE UPDATE OR DELETE ON china_payment_verification_artifacts
FOR EACH ROW EXECUTE FUNCTION china_payment_reject_verification_artifact_mutation();

CREATE OR REPLACE FUNCTION china_payment_require_verified_notification()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  artifact china_payment_verification_artifacts%ROWTYPE;
BEGIN
  IF NEW.signature_verified IS NOT TRUE THEN
    IF NEW.verification_artifact_id IS NOT NULL THEN
      RAISE EXCEPTION 'unverified payment notification cannot reference trusted verification artifact'
        USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
  END IF;

  IF NEW.verification_artifact_id IS NULL THEN
    RAISE EXCEPTION 'verified payment notification requires trusted verification artifact'
      USING ERRCODE = '23514';
  END IF;

  SELECT *
    INTO artifact
    FROM china_payment_verification_artifacts
   WHERE id = NEW.verification_artifact_id
     AND organization_id = NEW.organization_id
     AND project_id = NEW.project_id
     AND merchant_application_id = NEW.merchant_application_id
     AND provider = NEW.provider
     AND mode = NEW.mode
     AND provider_notification_id = NEW.provider_notification_id
     AND notification_type = NEW.notification_type
     AND payload_sha256 = NEW.payload_sha256
     AND headers_sha256 IS NOT DISTINCT FROM NEW.headers_sha256
     AND result = 'verified'
     AND verified_at <= COALESCE(NEW.received_at, now())
     AND fresh_until >= COALESCE(NEW.received_at, now());

  IF NOT FOUND THEN
    RAISE EXCEPTION 'payment notification verification artifact does not match notification scope and digests'
      USING ERRCODE = '23514';
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS china_payment_notifications_require_artifact
  ON china_payment_provider_notifications;
CREATE TRIGGER china_payment_notifications_require_artifact
BEFORE INSERT ON china_payment_provider_notifications
FOR EACH ROW EXECUTE FUNCTION china_payment_require_verified_notification();

CREATE OR REPLACE FUNCTION china_payment_transition_artifact_id()
RETURNS UUID
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  value TEXT;
BEGIN
  value := NULLIF(current_setting('app.a1_payment_verification_artifact_id', TRUE), '');
  IF value IS NULL THEN
    RETURN NULL;
  END IF;
  RETURN value::UUID;
EXCEPTION
  WHEN invalid_text_representation THEN
    RAISE EXCEPTION 'invalid payment verification artifact context'
      USING ERRCODE = '22023';
END;
$$;

CREATE OR REPLACE FUNCTION china_payment_require_verified_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  artifact_id UUID;
  target_kind_value TEXT;
  protected_statuses TEXT[];
  linked_order_id UUID;
BEGIN
  IF TG_TABLE_NAME = 'china_payment_orders' THEN
    target_kind_value := 'order';
    protected_statuses := ARRAY['paid', 'closed', 'expired', 'failed'];
    linked_order_id := NEW.id;
  ELSIF TG_TABLE_NAME = 'china_payment_refunds' THEN
    target_kind_value := 'refund';
    protected_statuses := ARRAY['succeeded', 'failed', 'closed'];
    linked_order_id := NEW.order_id;
  ELSE
    RAISE EXCEPTION 'unsupported payment transition table %', TG_TABLE_NAME;
  END IF;

  IF TG_OP = 'UPDATE' AND NEW.status IS NOT DISTINCT FROM OLD.status THEN
    RETURN NEW;
  END IF;
  IF NEW.status <> ALL(protected_statuses) THEN
    RETURN NEW;
  END IF;

  artifact_id := china_payment_transition_artifact_id();
  IF artifact_id IS NULL THEN
    RAISE EXCEPTION 'provider-authoritative payment status transition requires trusted verification artifact'
      USING ERRCODE = '42501';
  END IF;

  PERFORM 1
    FROM china_payment_verification_artifacts artifact
    JOIN china_payment_provider_notifications notification
      ON notification.verification_artifact_id = artifact.id
     AND notification.organization_id = artifact.organization_id
     AND notification.project_id = artifact.project_id
   WHERE artifact.id = artifact_id
     AND artifact.organization_id = NEW.organization_id
     AND artifact.project_id = NEW.project_id
     AND artifact.provider = NEW.provider
     AND artifact.mode = NEW.mode
     AND artifact.target_kind = target_kind_value
     AND artifact.target_id = NEW.id
     AND artifact.authorized_status = NEW.status
     AND artifact.result = 'verified'
     AND artifact.fresh_until >= now()
     AND notification.signature_verified IS TRUE
     AND notification.order_id = linked_order_id
   FOR SHARE OF artifact, notification;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'trusted verification artifact is missing, stale, consumed by another notification, or out of scope'
      USING ERRCODE = '42501';
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS china_payment_orders_require_verified_transition
  ON china_payment_orders;
CREATE TRIGGER china_payment_orders_require_verified_transition
BEFORE INSERT OR UPDATE OF status ON china_payment_orders
FOR EACH ROW EXECUTE FUNCTION china_payment_require_verified_transition();

DROP TRIGGER IF EXISTS china_payment_refunds_require_verified_transition
  ON china_payment_refunds;
CREATE TRIGGER china_payment_refunds_require_verified_transition
BEFORE INSERT OR UPDATE OF status ON china_payment_refunds
FOR EACH ROW EXECUTE FUNCTION china_payment_require_verified_transition();

CREATE OR REPLACE FUNCTION apply_china_payment_verified_order_status(
  p_organization_id UUID,
  p_project_id UUID,
  p_order_id UUID,
  p_status TEXT,
  p_verification_artifact_id UUID,
  p_paid_at TIMESTAMPTZ DEFAULT NULL,
  p_closed_at TIMESTAMPTZ DEFAULT NULL
)
RETURNS china_payment_orders
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
  updated_order china_payment_orders%ROWTYPE;
BEGIN
  IF p_status NOT IN ('paid', 'closed', 'expired', 'failed') THEN
    RAISE EXCEPTION 'unsupported verified order status %', p_status;
  END IF;
  PERFORM set_config(
    'app.a1_payment_verification_artifact_id',
    p_verification_artifact_id::TEXT,
    TRUE
  );
  UPDATE china_payment_orders
     SET status = p_status,
         paid_at = CASE
           WHEN p_status = 'paid' THEN COALESCE(p_paid_at, now())
           ELSE paid_at
         END,
         closed_at = CASE
           WHEN p_status IN ('closed', 'expired') THEN COALESCE(p_closed_at, now())
           ELSE closed_at
         END
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_order_id
  RETURNING * INTO updated_order;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'payment order not found in tenant and project scope';
  END IF;
  RETURN updated_order;
END;
$$;

CREATE OR REPLACE FUNCTION apply_china_payment_verified_refund_status(
  p_organization_id UUID,
  p_project_id UUID,
  p_refund_id UUID,
  p_status TEXT,
  p_verification_artifact_id UUID,
  p_completed_at TIMESTAMPTZ DEFAULT NULL
)
RETURNS china_payment_refunds
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
  updated_refund china_payment_refunds%ROWTYPE;
BEGIN
  IF p_status NOT IN ('succeeded', 'failed', 'closed') THEN
    RAISE EXCEPTION 'unsupported verified refund status %', p_status;
  END IF;
  PERFORM set_config(
    'app.a1_payment_verification_artifact_id',
    p_verification_artifact_id::TEXT,
    TRUE
  );
  UPDATE china_payment_refunds
     SET status = p_status,
         completed_at = COALESCE(p_completed_at, now())
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_refund_id
  RETURNING * INTO updated_refund;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'payment refund not found in tenant and project scope';
  END IF;
  RETURN updated_refund;
END;
$$;

DROP POLICY IF EXISTS billing_accounts_organization_isolation ON billing_accounts;
DROP POLICY IF EXISTS billing_provider_events_organization_isolation ON billing_provider_events;
DROP POLICY IF EXISTS billing_ledger_events_organization_isolation ON billing_ledger_events;

CREATE POLICY billing_accounts_organization_isolation ON billing_accounts
  USING (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
  )
  WITH CHECK (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
  );
CREATE POLICY billing_provider_events_organization_isolation ON billing_provider_events
  USING (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
  )
  WITH CHECK (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
  );
CREATE POLICY billing_ledger_events_organization_isolation ON billing_ledger_events
  USING (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
  )
  WITH CHECK (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
  );

DROP POLICY IF EXISTS china_payment_merchant_applications_organization_isolation
  ON china_payment_merchant_applications;
DROP POLICY IF EXISTS china_payment_config_refs_organization_isolation
  ON china_payment_config_refs;
DROP POLICY IF EXISTS china_payment_acquirer_account_bindings_organization_isolation
  ON china_payment_acquirer_account_bindings;
DROP POLICY IF EXISTS china_payment_orders_organization_isolation ON china_payment_orders;
DROP POLICY IF EXISTS china_payment_provider_notifications_organization_isolation
  ON china_payment_provider_notifications;
DROP POLICY IF EXISTS china_payment_refunds_organization_isolation ON china_payment_refunds;
DROP POLICY IF EXISTS china_payment_daily_bill_files_organization_isolation
  ON china_payment_daily_bill_files;
DROP POLICY IF EXISTS china_payment_daily_bill_lines_organization_isolation
  ON china_payment_daily_bill_lines;
DROP POLICY IF EXISTS china_payment_recon_discrepancies_org_isolation
  ON china_payment_reconciliation_discrepancies;
DROP POLICY IF EXISTS china_payment_ledger_links_organization_isolation
  ON china_payment_ledger_links;
DROP POLICY IF EXISTS china_payment_mutation_events_organization_isolation
  ON china_payment_mutation_events;
DROP POLICY IF EXISTS china_payment_verification_artifacts_project_isolation
  ON china_payment_verification_artifacts;

CREATE POLICY china_payment_merchant_applications_organization_isolation
  ON china_payment_merchant_applications
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY china_payment_config_refs_organization_isolation
  ON china_payment_config_refs
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY china_payment_acquirer_account_bindings_organization_isolation
  ON china_payment_acquirer_account_bindings
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY china_payment_orders_organization_isolation ON china_payment_orders
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY china_payment_provider_notifications_organization_isolation
  ON china_payment_provider_notifications
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY china_payment_refunds_organization_isolation ON china_payment_refunds
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY china_payment_daily_bill_files_organization_isolation
  ON china_payment_daily_bill_files
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY china_payment_daily_bill_lines_organization_isolation
  ON china_payment_daily_bill_lines
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY china_payment_recon_discrepancies_org_isolation
  ON china_payment_reconciliation_discrepancies
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY china_payment_ledger_links_organization_isolation
  ON china_payment_ledger_links
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY china_payment_mutation_events_organization_isolation
  ON china_payment_mutation_events
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY china_payment_verification_artifacts_project_isolation
  ON china_payment_verification_artifacts
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());

ALTER TABLE billing_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_provider_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_ledger_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_accounts FORCE ROW LEVEL SECURITY;
ALTER TABLE billing_provider_events FORCE ROW LEVEL SECURITY;
ALTER TABLE billing_ledger_events FORCE ROW LEVEL SECURITY;

COMMIT;
