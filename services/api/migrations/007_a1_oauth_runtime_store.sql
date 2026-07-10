-- A1 durable OAuth runtime store.
-- Runtime rows contain only SHA-256 digests and opaque external-secret references.

BEGIN;

CREATE TABLE IF NOT EXISTS oauth_runtime_transactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  provider TEXT NOT NULL CHECK (provider ~ '^[a-z][a-z0-9_-]{1,31}$'),
  state_digest TEXT NOT NULL CHECK (state_digest ~ '^[a-f0-9]{64}$'),
  binding_digest TEXT NOT NULL CHECK (binding_digest ~ '^[a-f0-9]{64}$'),
  transaction_ref TEXT NOT NULL CHECK (a1_oauth_reference_only(transaction_ref)),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'consumed', 'expired', 'failed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  failure_code TEXT,
  CONSTRAINT oauth_runtime_transactions_ttl_check CHECK (expires_at > created_at),
  CONSTRAINT oauth_runtime_transactions_status_time_check CHECK (
    (status = 'consumed' AND consumed_at IS NOT NULL)
    OR (status <> 'consumed' AND consumed_at IS NULL)
  ),
  CONSTRAINT oauth_runtime_transactions_scope_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT oauth_runtime_transactions_state_key UNIQUE (provider, state_digest),
  CONSTRAINT oauth_runtime_transactions_project_scope_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS oauth_runtime_transactions_pending_expiry_idx
  ON oauth_runtime_transactions(organization_id, project_id, expires_at)
  WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS oauth_replay_ledger (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  provider TEXT NOT NULL CHECK (provider ~ '^[a-z][a-z0-9_-]{1,31}$'),
  replay_kind TEXT NOT NULL CHECK (replay_kind IN ('state', 'authorization_code')),
  value_digest TEXT NOT NULL CHECK (value_digest ~ '^[a-f0-9]{64}$'),
  transaction_id UUID,
  observed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  expires_at TIMESTAMPTZ NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_oauth_public_metadata(metadata)),
  CONSTRAINT oauth_replay_ledger_ttl_check CHECK (expires_at > observed_at),
  CONSTRAINT oauth_replay_ledger_digest_key
    UNIQUE (provider, replay_kind, value_digest),
  CONSTRAINT oauth_replay_ledger_transaction_scope_fk FOREIGN KEY (
    organization_id, project_id, transaction_id
  ) REFERENCES oauth_runtime_transactions(
    organization_id, project_id, id
  ) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS oauth_replay_ledger_scope_expiry_idx
  ON oauth_replay_ledger(organization_id, project_id, expires_at);

CREATE TABLE IF NOT EXISTS oauth_token_opaque_refs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  provider TEXT NOT NULL CHECK (provider ~ '^[a-z][a-z0-9_-]{1,31}$'),
  binding_digest TEXT NOT NULL CHECK (binding_digest ~ '^[a-f0-9]{64}$'),
  opaque_ref TEXT NOT NULL CHECK (a1_oauth_reference_only(opaque_ref)),
  opaque_ref_digest TEXT NOT NULL CHECK (opaque_ref_digest ~ '^[a-f0-9]{64}$'),
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'superseded', 'revocation_pending', 'revoked', 'expired')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  expires_at TIMESTAMPTZ,
  superseded_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  CONSTRAINT oauth_token_opaque_refs_status_time_check CHECK (
    (status = 'superseded' AND superseded_at IS NOT NULL)
    OR (status = 'revoked' AND revoked_at IS NOT NULL)
    OR status IN ('active', 'revocation_pending', 'expired')
  ),
  CONSTRAINT oauth_token_opaque_refs_scope_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT oauth_token_opaque_refs_ref_key UNIQUE (opaque_ref_digest),
  CONSTRAINT oauth_token_opaque_refs_project_scope_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS oauth_token_opaque_refs_binding_idx
  ON oauth_token_opaque_refs(
    organization_id, project_id, provider, binding_digest, created_at DESC
  );

CREATE TABLE IF NOT EXISTS oauth_account_connections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  provider TEXT NOT NULL CHECK (provider ~ '^[a-z][a-z0-9_-]{1,31}$'),
  account_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  binding_digest TEXT NOT NULL CHECK (binding_digest ~ '^[a-f0-9]{64}$'),
  provider_subject_digest TEXT NOT NULL CHECK (provider_subject_digest ~ '^[a-f0-9]{64}$'),
  provider_login TEXT NOT NULL,
  email_digest TEXT CHECK (email_digest IS NULL OR email_digest ~ '^[a-f0-9]{64}$'),
  email_present BOOLEAN NOT NULL DEFAULT false,
  token_ref_id UUID NOT NULL,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'reauthorization_required', 'disconnected')),
  connected_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  disconnected_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_oauth_public_metadata(metadata)),
  CONSTRAINT oauth_account_connections_status_time_check CHECK (
    (status = 'disconnected' AND disconnected_at IS NOT NULL)
    OR (status <> 'disconnected' AND disconnected_at IS NULL)
  ),
  CONSTRAINT oauth_account_connections_scope_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT oauth_account_connections_binding_key
    UNIQUE (organization_id, project_id, provider, account_id),
  CONSTRAINT oauth_account_connections_subject_key
    UNIQUE (organization_id, project_id, provider, provider_subject_digest),
  CONSTRAINT oauth_account_connections_token_scope_fk FOREIGN KEY (
    organization_id, project_id, token_ref_id
  ) REFERENCES oauth_token_opaque_refs(
    organization_id, project_id, id
  ) ON DELETE RESTRICT,
  CONSTRAINT oauth_account_connections_project_scope_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS oauth_account_connections_user_idx
  ON oauth_account_connections(
    organization_id, project_id, user_id, provider, status
  );

CREATE TABLE IF NOT EXISTS oauth_revocation_outbox (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  provider TEXT NOT NULL CHECK (provider ~ '^[a-z][a-z0-9_-]{1,31}$'),
  connection_id UUID,
  token_ref_id UUID NOT NULL,
  reason_code TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'leased', 'delivered', 'dead_letter')),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  max_attempts INTEGER NOT NULL DEFAULT 12 CHECK (max_attempts > 0),
  available_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  lease_owner TEXT,
  lease_expires_at TIMESTAMPTZ,
  delivered_at TIMESTAMPTZ,
  last_error_code TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT oauth_revocation_outbox_delivery_check CHECK (
    (status = 'delivered' AND delivered_at IS NOT NULL)
    OR (status <> 'delivered' AND delivered_at IS NULL)
  ),
  CONSTRAINT oauth_revocation_outbox_lease_check CHECK (
    (status = 'leased' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
    OR (status <> 'leased' AND lease_owner IS NULL AND lease_expires_at IS NULL)
  ),
  CONSTRAINT oauth_revocation_outbox_token_key UNIQUE (token_ref_id),
  CONSTRAINT oauth_revocation_outbox_connection_scope_fk FOREIGN KEY (
    organization_id, project_id, connection_id
  ) REFERENCES oauth_account_connections(
    organization_id, project_id, id
  ) ON DELETE RESTRICT,
  CONSTRAINT oauth_revocation_outbox_token_scope_fk FOREIGN KEY (
    organization_id, project_id, token_ref_id
  ) REFERENCES oauth_token_opaque_refs(
    organization_id, project_id, id
  ) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS oauth_revocation_outbox_ready_idx
  ON oauth_revocation_outbox(available_at, created_at)
  WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS oauth_runtime_audit (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id UUID,
  event_digest TEXT NOT NULL CHECK (event_digest ~ '^[a-f0-9]{64}$'),
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_oauth_public_metadata(metadata)),
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT oauth_runtime_audit_digest_key UNIQUE (event_digest),
  CONSTRAINT oauth_runtime_audit_project_scope_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS oauth_runtime_audit_scope_created_idx
  ON oauth_runtime_audit(organization_id, project_id, created_at DESC);

CREATE OR REPLACE FUNCTION a1_oauth_runtime_audit_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  target_id UUID;
  target_organization_id UUID;
  target_project_id UUID;
  safe_metadata JSONB;
  event_seed TEXT;
BEGIN
  target_id := COALESCE(NEW.id, OLD.id);
  target_organization_id := COALESCE(NEW.organization_id, OLD.organization_id);
  target_project_id := COALESCE(NEW.project_id, OLD.project_id);
  safe_metadata := jsonb_build_object(
    'operation', TG_OP,
    'table', TG_TABLE_NAME
  );
  event_seed := concat_ws(
    ':', target_organization_id, target_project_id, TG_TABLE_NAME,
    target_id, TG_OP, clock_timestamp()
  );
  INSERT INTO oauth_runtime_audit (
    organization_id, project_id, action, resource_type,
    resource_id, event_digest, metadata
  ) VALUES (
    target_organization_id,
    target_project_id,
    'oauth.runtime.' || lower(TG_OP),
    TG_TABLE_NAME,
    target_id,
    a1_oauth_digest(event_seed),
    safe_metadata
  );
  RETURN COALESCE(NEW, OLD);
END;
$$;

CREATE OR REPLACE FUNCTION a1_consume_oauth_runtime_transaction(
  p_provider TEXT,
  p_state_digest TEXT,
  p_consumed_at TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS oauth_runtime_transactions
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  target oauth_runtime_transactions%ROWTYPE;
BEGIN
  PERFORM a1_assert_role_nobypassrls(session_user);
  IF p_state_digest !~ '^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION 'oauth state digest must be sha256 hex'
      USING ERRCODE = '22023';
  END IF;

  SELECT *
    INTO target
    FROM oauth_runtime_transactions
   WHERE provider = p_provider
     AND state_digest = p_state_digest
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'oauth runtime transaction not found'
      USING ERRCODE = 'P0002';
  END IF;
  IF target.status <> 'pending' OR target.consumed_at IS NOT NULL THEN
    RAISE EXCEPTION 'oauth runtime transaction already consumed'
      USING ERRCODE = '23505';
  END IF;
  IF target.expires_at <= p_consumed_at THEN
    UPDATE oauth_runtime_transactions
       SET status = 'expired', failure_code = 'expired'
     WHERE id = target.id;
    SELECT *
      INTO target
      FROM oauth_runtime_transactions
     WHERE id = target.id;
    RETURN target;
  END IF;

  INSERT INTO oauth_replay_ledger (
    organization_id, project_id, provider, replay_kind,
    value_digest, transaction_id, observed_at, expires_at
  ) VALUES (
    target.organization_id, target.project_id, target.provider, 'state',
    target.state_digest, target.id, p_consumed_at,
    GREATEST(target.expires_at, p_consumed_at + INTERVAL '24 hours')
  );

  UPDATE oauth_runtime_transactions
     SET status = 'consumed',
         consumed_at = p_consumed_at,
         failure_code = NULL
   WHERE id = target.id
  RETURNING * INTO target;
  RETURN target;
END;
$$;

CREATE OR REPLACE FUNCTION a1_revoke_oauth_token_ref(
  p_opaque_ref_digest TEXT,
  p_revoked_at TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS oauth_token_opaque_refs
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  target oauth_token_opaque_refs%ROWTYPE;
BEGIN
  PERFORM a1_assert_role_nobypassrls(session_user);
  IF p_opaque_ref_digest !~ '^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION 'oauth opaque reference digest must be sha256 hex'
      USING ERRCODE = '22023';
  END IF;

  UPDATE oauth_token_opaque_refs
     SET status = 'revoked',
         revoked_at = COALESCE(revoked_at, p_revoked_at)
   WHERE opaque_ref_digest = p_opaque_ref_digest
     AND status <> 'revoked'
  RETURNING * INTO target;
  IF FOUND THEN
    RETURN target;
  END IF;

  SELECT *
    INTO target
    FROM oauth_token_opaque_refs
   WHERE opaque_ref_digest = p_opaque_ref_digest;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'oauth opaque token reference not found'
      USING ERRCODE = 'P0002';
  END IF;
  RETURN target;
END;
$$;

CREATE OR REPLACE FUNCTION a1_claim_oauth_revocation_outbox(
  p_organization_id UUID,
  p_project_id UUID,
  p_lease_owner TEXT,
  p_limit INTEGER DEFAULT 25,
  p_lease_seconds INTEGER DEFAULT 60,
  p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS SETOF oauth_revocation_outbox
LANGUAGE plpgsql
AS $$
BEGIN
  PERFORM a1_oauth_assert_runtime_context(p_organization_id, p_project_id);
  IF btrim(COALESCE(p_lease_owner, '')) = ''
     OR p_limit < 1 OR p_limit > 500
     OR p_lease_seconds < 5 OR p_lease_seconds > 3600 THEN
    RAISE EXCEPTION 'invalid oauth revocation lease request'
      USING ERRCODE = '22023';
  END IF;

  RETURN QUERY
  WITH candidates AS (
    SELECT id
      FROM oauth_revocation_outbox
     WHERE organization_id = p_organization_id
       AND project_id = p_project_id
       AND status = 'pending'
       AND available_at <= p_now
     ORDER BY available_at, created_at
     FOR UPDATE SKIP LOCKED
     LIMIT p_limit
  )
  UPDATE oauth_revocation_outbox AS target
     SET status = 'leased',
         attempts = target.attempts + 1,
         lease_owner = p_lease_owner,
         lease_expires_at = p_now + make_interval(secs => p_lease_seconds),
         updated_at = p_now
    FROM candidates
   WHERE target.id = candidates.id
  RETURNING target.*;
END;
$$;

DROP TRIGGER IF EXISTS oauth_runtime_transactions_audit ON oauth_runtime_transactions;
CREATE TRIGGER oauth_runtime_transactions_audit
AFTER INSERT OR UPDATE ON oauth_runtime_transactions
FOR EACH ROW EXECUTE FUNCTION a1_oauth_runtime_audit_change();

DROP TRIGGER IF EXISTS oauth_token_opaque_refs_audit ON oauth_token_opaque_refs;
CREATE TRIGGER oauth_token_opaque_refs_audit
AFTER INSERT OR UPDATE ON oauth_token_opaque_refs
FOR EACH ROW EXECUTE FUNCTION a1_oauth_runtime_audit_change();

DROP TRIGGER IF EXISTS oauth_account_connections_audit ON oauth_account_connections;
CREATE TRIGGER oauth_account_connections_audit
AFTER INSERT OR UPDATE ON oauth_account_connections
FOR EACH ROW EXECUTE FUNCTION a1_oauth_runtime_audit_change();

DROP TRIGGER IF EXISTS oauth_revocation_outbox_audit ON oauth_revocation_outbox;
CREATE TRIGGER oauth_revocation_outbox_audit
AFTER INSERT OR UPDATE ON oauth_revocation_outbox
FOR EACH ROW EXECUTE FUNCTION a1_oauth_runtime_audit_change();

DROP TRIGGER IF EXISTS oauth_replay_ledger_append_only ON oauth_replay_ledger;
CREATE TRIGGER oauth_replay_ledger_append_only
BEFORE UPDATE OR DELETE ON oauth_replay_ledger
FOR EACH ROW EXECUTE FUNCTION a1_oauth_reject_append_only_mutation();

DROP TRIGGER IF EXISTS oauth_runtime_audit_append_only ON oauth_runtime_audit;
CREATE TRIGGER oauth_runtime_audit_append_only
BEFORE UPDATE OR DELETE ON oauth_runtime_audit
FOR EACH ROW EXECUTE FUNCTION a1_oauth_reject_append_only_mutation();

ALTER TABLE oauth_runtime_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_replay_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_token_opaque_refs ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_account_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_revocation_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_runtime_audit ENABLE ROW LEVEL SECURITY;

ALTER TABLE oauth_runtime_transactions FORCE ROW LEVEL SECURITY;
ALTER TABLE oauth_replay_ledger FORCE ROW LEVEL SECURITY;
ALTER TABLE oauth_token_opaque_refs FORCE ROW LEVEL SECURITY;
ALTER TABLE oauth_account_connections FORCE ROW LEVEL SECURITY;
ALTER TABLE oauth_revocation_outbox FORCE ROW LEVEL SECURITY;
ALTER TABLE oauth_runtime_audit FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS oauth_runtime_transactions_tenant_isolation
  ON oauth_runtime_transactions;
DROP POLICY IF EXISTS oauth_replay_ledger_tenant_isolation
  ON oauth_replay_ledger;
DROP POLICY IF EXISTS oauth_token_opaque_refs_tenant_isolation
  ON oauth_token_opaque_refs;
DROP POLICY IF EXISTS oauth_account_connections_tenant_isolation
  ON oauth_account_connections;
DROP POLICY IF EXISTS oauth_revocation_outbox_tenant_isolation
  ON oauth_revocation_outbox;
DROP POLICY IF EXISTS oauth_runtime_audit_tenant_isolation
  ON oauth_runtime_audit;

CREATE POLICY oauth_runtime_transactions_tenant_isolation
  ON oauth_runtime_transactions
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY oauth_replay_ledger_tenant_isolation
  ON oauth_replay_ledger
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY oauth_token_opaque_refs_tenant_isolation
  ON oauth_token_opaque_refs
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY oauth_account_connections_tenant_isolation
  ON oauth_account_connections
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY oauth_revocation_outbox_tenant_isolation
  ON oauth_revocation_outbox
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY oauth_runtime_audit_tenant_isolation
  ON oauth_runtime_audit
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());

REVOKE ALL ON FUNCTION a1_consume_oauth_runtime_transaction(
  TEXT, TEXT, TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_revoke_oauth_token_ref(
  TEXT, TIMESTAMPTZ
) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a1_runtime') THEN
    GRANT EXECUTE ON FUNCTION a1_consume_oauth_runtime_transaction(
      TEXT, TEXT, TIMESTAMPTZ
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_revoke_oauth_token_ref(
      TEXT, TIMESTAMPTZ
    ) TO a1_runtime;
  END IF;
END;
$$;

COMMIT;
