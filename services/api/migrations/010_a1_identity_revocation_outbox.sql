-- A1 fenced provider revocation and superseded-token cleanup outbox.
-- Provider calls and vault deletion happen outside PostgreSQL; this migration
-- owns durable leasing and atomic local completion only.

BEGIN;

ALTER TABLE oauth_revocation_outbox
  ADD COLUMN IF NOT EXISTS lease_generation BIGINT NOT NULL DEFAULT 0
    CHECK (lease_generation >= 0),
  ADD COLUMN IF NOT EXISTS provider_revoked_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS vault_deleted_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS dead_lettered_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS cleanup_completed_at TIMESTAMPTZ;

ALTER TABLE oauth_revocation_outbox
  DROP CONSTRAINT IF EXISTS oauth_revocation_outbox_terminal_time_check;
ALTER TABLE oauth_revocation_outbox
  ADD CONSTRAINT oauth_revocation_outbox_terminal_time_check CHECK (
    (status = 'delivered'
      AND delivered_at IS NOT NULL
      AND cleanup_completed_at IS NOT NULL
      AND provider_revoked_at IS NOT NULL
      AND vault_deleted_at IS NOT NULL
      AND dead_lettered_at IS NULL)
    OR (status = 'dead_letter'
      AND dead_lettered_at IS NOT NULL
      AND delivered_at IS NULL
      AND cleanup_completed_at IS NULL)
    OR (status IN ('pending', 'leased')
      AND delivered_at IS NULL
      AND dead_lettered_at IS NULL
      AND cleanup_completed_at IS NULL)
  );

CREATE INDEX IF NOT EXISTS oauth_revocation_outbox_expired_lease_idx
  ON oauth_revocation_outbox(lease_expires_at, created_at)
  WHERE status = 'leased';

CREATE OR REPLACE FUNCTION a1_claim_identity_revocation_outbox(
  p_organization_id UUID,
  p_project_id UUID,
  p_lease_owner TEXT,
  p_limit INTEGER DEFAULT 25,
  p_lease_seconds INTEGER DEFAULT 60,
  p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS TABLE (
  outbox_id UUID,
  organization_id UUID,
  project_id UUID,
  provider TEXT,
  connection_id UUID,
  token_ref_id UUID,
  opaque_ref TEXT,
  operation_kind TEXT,
  reason_code TEXT,
  attempts INTEGER,
  max_attempts INTEGER,
  lease_owner TEXT,
  lease_generation BIGINT,
  lease_expires_at TIMESTAMPTZ,
  provider_revoked_at TIMESTAMPTZ,
  vault_deleted_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
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
    SELECT target.id
      FROM oauth_revocation_outbox AS target
     WHERE target.organization_id = p_organization_id
       AND target.project_id = p_project_id
       AND (
         (target.status = 'pending' AND target.available_at <= p_now)
         OR (target.status = 'leased' AND target.lease_expires_at <= p_now)
       )
       AND target.attempts < target.max_attempts
     ORDER BY target.available_at, target.created_at
     FOR UPDATE SKIP LOCKED
     LIMIT p_limit
  ),
  claimed AS (
    UPDATE oauth_revocation_outbox AS target
       SET status = 'leased',
           attempts = target.attempts + 1,
           lease_owner = p_lease_owner,
           lease_expires_at = p_now + make_interval(secs => p_lease_seconds),
           lease_generation = target.lease_generation + 1,
           last_error_code = NULL,
           updated_at = p_now
      FROM candidates
     WHERE target.id = candidates.id
    RETURNING target.*
  )
  SELECT
    claimed.id, claimed.organization_id, claimed.project_id,
    claimed.provider, claimed.connection_id, claimed.token_ref_id,
    token_ref.opaque_ref, claimed.operation_kind, claimed.reason_code,
    claimed.attempts, claimed.max_attempts, claimed.lease_owner,
    claimed.lease_generation, claimed.lease_expires_at,
    claimed.provider_revoked_at, claimed.vault_deleted_at
    FROM claimed
    JOIN oauth_token_opaque_refs AS token_ref
      ON token_ref.organization_id = claimed.organization_id
     AND token_ref.project_id = claimed.project_id
     AND token_ref.id = claimed.token_ref_id;
END;
$$;

CREATE OR REPLACE FUNCTION a1_mark_identity_revocation_provider_revoked(
  p_organization_id UUID,
  p_project_id UUID,
  p_outbox_id UUID,
  p_lease_owner TEXT,
  p_lease_generation BIGINT,
  p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS oauth_revocation_outbox
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  target oauth_revocation_outbox%ROWTYPE;
BEGIN
  PERFORM a1_oauth_assert_runtime_context(p_organization_id, p_project_id);
  SELECT *
    INTO target
    FROM oauth_revocation_outbox
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_outbox_id
   FOR UPDATE;
  IF NOT FOUND
     OR target.status <> 'leased'
     OR target.lease_owner <> p_lease_owner
     OR target.lease_generation <> p_lease_generation
     OR target.lease_expires_at <= p_now THEN
    RAISE EXCEPTION 'oauth revocation lease lost'
      USING ERRCODE = '40001';
  END IF;

  UPDATE oauth_revocation_outbox
     SET provider_revoked_at = COALESCE(provider_revoked_at, p_now),
         updated_at = p_now
   WHERE id = target.id
  RETURNING * INTO target;
  RETURN target;
END;
$$;

CREATE OR REPLACE FUNCTION a1_mark_identity_revocation_vault_deleted(
  p_organization_id UUID,
  p_project_id UUID,
  p_outbox_id UUID,
  p_lease_owner TEXT,
  p_lease_generation BIGINT,
  p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS oauth_revocation_outbox
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  target oauth_revocation_outbox%ROWTYPE;
BEGIN
  PERFORM a1_oauth_assert_runtime_context(p_organization_id, p_project_id);
  SELECT *
    INTO target
    FROM oauth_revocation_outbox
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_outbox_id
   FOR UPDATE;
  IF NOT FOUND
     OR target.status <> 'leased'
     OR target.lease_owner <> p_lease_owner
     OR target.lease_generation <> p_lease_generation
     OR target.lease_expires_at <= p_now THEN
    RAISE EXCEPTION 'oauth revocation lease lost'
      USING ERRCODE = '40001';
  END IF;
  IF target.provider_revoked_at IS NULL THEN
    RAISE EXCEPTION 'oauth provider revocation is not checkpointed'
      USING ERRCODE = '23514';
  END IF;

  UPDATE oauth_revocation_outbox
     SET vault_deleted_at = COALESCE(vault_deleted_at, p_now),
         updated_at = p_now
   WHERE id = target.id
  RETURNING * INTO target;
  RETURN target;
END;
$$;

CREATE OR REPLACE FUNCTION a1_complete_identity_revocation_outbox(
  p_organization_id UUID,
  p_project_id UUID,
  p_outbox_id UUID,
  p_lease_owner TEXT,
  p_lease_generation BIGINT,
  p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS oauth_revocation_outbox
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  target oauth_revocation_outbox%ROWTYPE;
BEGIN
  PERFORM a1_oauth_assert_runtime_context(p_organization_id, p_project_id);
  SELECT *
    INTO target
    FROM oauth_revocation_outbox
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_outbox_id
   FOR UPDATE;
  IF NOT FOUND
     OR target.status <> 'leased'
     OR target.lease_owner <> p_lease_owner
     OR target.lease_generation <> p_lease_generation
     OR target.lease_expires_at <= p_now
     OR target.provider_revoked_at IS NULL
     OR target.vault_deleted_at IS NULL THEN
    RAISE EXCEPTION 'oauth revocation lease lost'
      USING ERRCODE = '40001';
  END IF;

  UPDATE oauth_token_opaque_refs
     SET status = 'revoked',
         revoked_at = COALESCE(revoked_at, p_now)
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = target.token_ref_id
     AND status IN ('active', 'superseded', 'revocation_pending');

  -- A reconnect may have moved the connection to a new token. Only the
  -- connection still bound to this revoked token is locally disconnected.
  UPDATE oauth_account_connections
     SET status = 'disconnected',
         disconnected_at = COALESCE(disconnected_at, p_now),
         updated_at = p_now
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = target.connection_id
     AND token_ref_id = target.token_ref_id
     AND status = 'revocation_pending';

  UPDATE oauth_revocation_outbox
     SET status = 'delivered',
         delivered_at = p_now,
         cleanup_completed_at = p_now,
         lease_owner = NULL,
         lease_expires_at = NULL,
         last_error_code = NULL,
         updated_at = p_now
   WHERE id = target.id
  RETURNING * INTO target;
  RETURN target;
END;
$$;

CREATE OR REPLACE FUNCTION a1_retry_identity_revocation_outbox(
  p_organization_id UUID,
  p_project_id UUID,
  p_outbox_id UUID,
  p_lease_owner TEXT,
  p_lease_generation BIGINT,
  p_error_code TEXT,
  p_base_backoff_seconds BIGINT,
  p_max_backoff_seconds BIGINT,
  p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS oauth_revocation_outbox
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  target oauth_revocation_outbox%ROWTYPE;
  retry_seconds BIGINT;
BEGIN
  PERFORM a1_oauth_assert_runtime_context(p_organization_id, p_project_id);
  IF p_error_code !~ '^[a-z][a-z0-9_.-]{1,63}$'
     OR p_base_backoff_seconds < 1
     OR p_max_backoff_seconds < p_base_backoff_seconds
     OR p_max_backoff_seconds > 86400 THEN
    RAISE EXCEPTION 'invalid oauth revocation retry request'
      USING ERRCODE = '22023';
  END IF;

  SELECT *
    INTO target
    FROM oauth_revocation_outbox
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_outbox_id
   FOR UPDATE;
  IF NOT FOUND
     OR target.status <> 'leased'
     OR target.lease_owner <> p_lease_owner
     OR target.lease_generation <> p_lease_generation THEN
    RAISE EXCEPTION 'oauth revocation lease lost'
      USING ERRCODE = '40001';
  END IF;

  IF target.attempts >= target.max_attempts THEN
    UPDATE oauth_revocation_outbox
       SET status = 'dead_letter',
           dead_lettered_at = p_now,
           lease_owner = NULL,
           lease_expires_at = NULL,
           last_error_code = p_error_code,
           updated_at = p_now
     WHERE id = target.id
    RETURNING * INTO target;
  ELSE
    retry_seconds := LEAST(
      p_max_backoff_seconds,
      p_base_backoff_seconds
        * (1::BIGINT << LEAST(GREATEST(target.attempts - 1, 0), 30))
    );
    UPDATE oauth_revocation_outbox
       SET status = 'pending',
           available_at = p_now
             + make_interval(secs => retry_seconds::DOUBLE PRECISION),
           lease_owner = NULL,
           lease_expires_at = NULL,
           last_error_code = p_error_code,
           updated_at = p_now
     WHERE id = target.id
    RETURNING * INTO target;
  END IF;
  RETURN target;
END;
$$;

REVOKE ALL ON FUNCTION a1_claim_identity_revocation_outbox(
  UUID, UUID, TEXT, INTEGER, INTEGER, TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_complete_identity_revocation_outbox(
  UUID, UUID, UUID, TEXT, BIGINT, TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_mark_identity_revocation_provider_revoked(
  UUID, UUID, UUID, TEXT, BIGINT, TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_mark_identity_revocation_vault_deleted(
  UUID, UUID, UUID, TEXT, BIGINT, TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_retry_identity_revocation_outbox(
  UUID, UUID, UUID, TEXT, BIGINT, TEXT, BIGINT, BIGINT, TIMESTAMPTZ
) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a1_runtime') THEN
    GRANT EXECUTE ON FUNCTION a1_claim_identity_revocation_outbox(
      UUID, UUID, TEXT, INTEGER, INTEGER, TIMESTAMPTZ
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_complete_identity_revocation_outbox(
      UUID, UUID, UUID, TEXT, BIGINT, TIMESTAMPTZ
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_mark_identity_revocation_provider_revoked(
      UUID, UUID, UUID, TEXT, BIGINT, TIMESTAMPTZ
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_mark_identity_revocation_vault_deleted(
      UUID, UUID, UUID, TEXT, BIGINT, TIMESTAMPTZ
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_retry_identity_revocation_outbox(
      UUID, UUID, UUID, TEXT, BIGINT, TEXT, BIGINT, BIGINT, TIMESTAMPTZ
    ) TO a1_runtime;
  END IF;
END;
$$;

COMMIT;
