-- Production identity-verification delivery leasing and audited redrive.
-- Destination and OTP material remain in an external vault. PostgreSQL stores
-- only an opaque vault reference and public-safe provider idempotency keys.

BEGIN;

CREATE OR REPLACE FUNCTION a1_identity_delivery_reference_only(
  p_reference TEXT
)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
  SELECT p_reference IS NOT NULL
    AND length(p_reference) BETWEEN 4 AND 1024
    AND p_reference ~
      '^(vault|env|kms|secret|provider-ref|opaque-ref):[A-Za-z0-9][A-Za-z0-9._:/-]+$';
$$;

CREATE OR REPLACE FUNCTION a1_identity_delivery_public_acceptance_reference(
  p_reference TEXT
)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
  SELECT p_reference IS NOT NULL
    AND length(p_reference) BETWEEN 1 AND 256
    AND p_reference ~
      '^(provider-ref|message-ref|receipt-ref):[A-Za-z0-9][A-Za-z0-9._:/-]*$';
$$;

ALTER TABLE identity_verification_delivery_outbox
  ADD COLUMN IF NOT EXISTS opaque_ref TEXT,
  ADD COLUMN IF NOT EXISTS provider_idempotency_key TEXT,
  ADD COLUMN IF NOT EXISTS provider_acceptance_ref TEXT,
  ADD COLUMN IF NOT EXISTS provider_accepted_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS max_attempts INTEGER NOT NULL DEFAULT 8,
  ADD COLUMN IF NOT EXISTS last_error_code TEXT,
  ADD COLUMN IF NOT EXISTS redriven_at TIMESTAMPTZ;

-- Migration 012 created rows before opaque delivery references existed. The
-- deterministic reference is a vault lookup key, not secret material. A 012
-- delivered row already asserted provider acceptance, so preserve that fact
-- with a bounded legacy reference and its original delivery timestamp.
UPDATE identity_verification_delivery_outbox
   SET opaque_ref = COALESCE(
         opaque_ref,
         'opaque-ref:identity-delivery/' || challenge_id::TEXT
       ),
       provider_idempotency_key = COALESCE(
         provider_idempotency_key,
         'identity-delivery:' || challenge_id::TEXT || ':0'
       ),
       provider_acceptance_ref = CASE
         WHEN status = 'delivered' THEN COALESCE(
           provider_acceptance_ref,
           'provider-ref:legacy/' || challenge_id::TEXT
         )
         ELSE NULL
       END,
       provider_accepted_at = CASE
         WHEN status = 'delivered' THEN COALESCE(
           provider_accepted_at,
           delivered_at
         )
         ELSE NULL
       END,
       max_attempts = GREATEST(max_attempts, attempt_count, 1),
       lease_generation = CASE
         WHEN status = 'leased' THEN GREATEST(lease_generation, 1)
         ELSE lease_generation
       END,
       lease_owner = CASE WHEN status = 'leased' THEN lease_owner END,
       lease_expires_at = CASE WHEN status = 'leased' THEN lease_expires_at END,
       delivered_at = CASE WHEN status = 'delivered' THEN delivered_at END,
       dead_at = CASE WHEN status = 'dead' THEN dead_at END;

ALTER TABLE identity_verification_delivery_outbox
  ALTER COLUMN opaque_ref SET NOT NULL,
  ALTER COLUMN provider_idempotency_key SET NOT NULL;

ALTER TABLE identity_verification_delivery_outbox
  DROP CONSTRAINT IF EXISTS identity_verification_delivery_opaque_ref_check;
ALTER TABLE identity_verification_delivery_outbox
  ADD CONSTRAINT identity_verification_delivery_opaque_ref_check CHECK (
    a1_identity_delivery_reference_only(opaque_ref)
  );

ALTER TABLE identity_verification_delivery_outbox
  DROP CONSTRAINT IF EXISTS identity_verification_delivery_provider_key_check;
ALTER TABLE identity_verification_delivery_outbox
  ADD CONSTRAINT identity_verification_delivery_provider_key_check CHECK (
    length(provider_idempotency_key) BETWEEN 8 AND 256
    AND provider_idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9._:-]+$'
  );

ALTER TABLE identity_verification_delivery_outbox
  DROP CONSTRAINT IF EXISTS identity_verification_delivery_acceptance_check;
ALTER TABLE identity_verification_delivery_outbox
  ADD CONSTRAINT identity_verification_delivery_acceptance_check CHECK (
    (
      provider_acceptance_ref IS NULL
      AND provider_accepted_at IS NULL
    )
    OR (
      provider_acceptance_ref IS NOT NULL
      AND provider_accepted_at IS NOT NULL
      AND a1_identity_delivery_public_acceptance_reference(
        provider_acceptance_ref
      )
    )
  );

ALTER TABLE identity_verification_delivery_outbox
  DROP CONSTRAINT IF EXISTS identity_verification_delivery_attempts_check;
ALTER TABLE identity_verification_delivery_outbox
  ADD CONSTRAINT identity_verification_delivery_attempts_check CHECK (
    max_attempts BETWEEN 1 AND 1000
    AND attempt_count BETWEEN 0 AND max_attempts
  );

ALTER TABLE identity_verification_delivery_outbox
  DROP CONSTRAINT IF EXISTS identity_verification_delivery_error_code_check;
ALTER TABLE identity_verification_delivery_outbox
  ADD CONSTRAINT identity_verification_delivery_error_code_check CHECK (
    last_error_code IS NULL
    OR last_error_code ~ '^[a-z][a-z0-9_.-]{1,63}$'
  );

ALTER TABLE identity_verification_delivery_outbox
  DROP CONSTRAINT IF EXISTS identity_verification_delivery_outbox_lease_check;
ALTER TABLE identity_verification_delivery_outbox
  ADD CONSTRAINT identity_verification_delivery_outbox_lease_check CHECK (
    (
      status = 'leased'
      AND lease_owner IS NOT NULL
      AND lease_generation > 0
      AND lease_expires_at IS NOT NULL
    )
    OR (
      status <> 'leased'
      AND lease_owner IS NULL
      AND lease_expires_at IS NULL
    )
  );

ALTER TABLE identity_verification_delivery_outbox
  DROP CONSTRAINT IF EXISTS identity_verification_delivery_outbox_terminal_check;
ALTER TABLE identity_verification_delivery_outbox
  ADD CONSTRAINT identity_verification_delivery_outbox_terminal_check CHECK (
    (
      status = 'delivered'
      AND delivered_at IS NOT NULL
      AND dead_at IS NULL
      AND provider_acceptance_ref IS NOT NULL
      AND provider_accepted_at IS NOT NULL
      AND provider_accepted_at <= delivered_at
    )
    OR (
      status = 'dead'
      AND dead_at IS NOT NULL
      AND delivered_at IS NULL
      AND provider_acceptance_ref IS NULL
      AND provider_accepted_at IS NULL
    )
    OR (
      status IN ('pending', 'leased', 'retry')
      AND delivered_at IS NULL
      AND dead_at IS NULL
      AND provider_acceptance_ref IS NULL
      AND provider_accepted_at IS NULL
    )
  );

CREATE UNIQUE INDEX IF NOT EXISTS
  identity_verification_delivery_scope_id_key
  ON identity_verification_delivery_outbox(organization_id, project_id, id);

CREATE UNIQUE INDEX IF NOT EXISTS
  identity_verification_delivery_provider_idempotency_key
  ON identity_verification_delivery_outbox(provider_idempotency_key);

CREATE INDEX IF NOT EXISTS identity_verification_delivery_expired_lease_idx
  ON identity_verification_delivery_outbox(
    organization_id, project_id, lease_expires_at, created_at
  )
  WHERE status = 'leased';

CREATE TABLE IF NOT EXISTS identity_verification_delivery_redrive_audit (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  outbox_id UUID NOT NULL,
  actor_id TEXT NOT NULL CHECK (
    length(actor_id) BETWEEN 1 AND 256
    AND actor_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'
  ),
  reason_code TEXT NOT NULL CHECK (
    reason_code ~ '^[a-z][a-z0-9_.-]{1,63}$'
  ),
  request_id TEXT NOT NULL CHECK (
    length(request_id) BETWEEN 1 AND 256
    AND request_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'
  ),
  previous_lease_generation BIGINT NOT NULL CHECK (
    previous_lease_generation > 0
  ),
  new_lease_generation BIGINT NOT NULL CHECK (
    new_lease_generation = previous_lease_generation + 1
  ),
  provider_idempotency_key TEXT NOT NULL CHECK (
    length(provider_idempotency_key) BETWEEN 8 AND 256
    AND provider_idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9._:-]+$'
  ),
  redriven_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT identity_verification_delivery_redrive_request_key UNIQUE (
    organization_id, project_id, request_id
  ),
  CONSTRAINT identity_verification_delivery_redrive_outbox_fk
    FOREIGN KEY (organization_id, project_id, outbox_id)
    REFERENCES identity_verification_delivery_outbox(
      organization_id, project_id, id
    ) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS identity_verification_delivery_redrive_audit_idx
  ON identity_verification_delivery_redrive_audit(
    organization_id, project_id, outbox_id, redriven_at DESC
  );

CREATE OR REPLACE FUNCTION a1_identity_delivery_assign_references()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF NEW.opaque_ref IS NULL THEN
    NEW.opaque_ref :=
      'opaque-ref:identity-delivery/' || NEW.challenge_id::TEXT;
  END IF;
  IF NEW.provider_idempotency_key IS NULL THEN
    NEW.provider_idempotency_key :=
      'identity-delivery:' || NEW.challenge_id::TEXT || ':0';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS identity_verification_delivery_assign_references
  ON identity_verification_delivery_outbox;
CREATE TRIGGER identity_verification_delivery_assign_references
BEFORE INSERT ON identity_verification_delivery_outbox
FOR EACH ROW EXECUTE FUNCTION a1_identity_delivery_assign_references();

DROP TRIGGER IF EXISTS identity_verification_delivery_redrive_append_only
  ON identity_verification_delivery_redrive_audit;
CREATE TRIGGER identity_verification_delivery_redrive_append_only
BEFORE UPDATE OR DELETE ON identity_verification_delivery_redrive_audit
FOR EACH ROW EXECUTE FUNCTION a1_identity_reject_append_only_mutation();

CREATE OR REPLACE FUNCTION a1_identity_delivery_assert_scope(
  p_organization_id UUID,
  p_project_id UUID
)
RETURNS VOID
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  PERFORM a1_identity_verification_assert_scope(
    p_organization_id, p_project_id
  );
END;
$$;

CREATE OR REPLACE FUNCTION a1_issue_identity_verification_challenge_with_delivery(
  p_organization_id UUID,
  p_project_id UUID,
  p_principal_id UUID,
  p_channel TEXT,
  p_purpose TEXT,
  p_subject_digest TEXT,
  p_challenge_digest TEXT,
  p_code_digest TEXT,
  p_request_context_digest TEXT,
  p_expires_at TIMESTAMPTZ,
  p_max_attempts INTEGER,
  p_cooldown_seconds INTEGER,
  p_event_digest TEXT,
  p_opaque_ref TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE (
  challenge_id UUID,
  accepted BOOLEAN,
  retry_after_seconds INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  issuance RECORD;
  updated_outbox_id UUID;
BEGIN
  PERFORM a1_identity_delivery_assert_scope(
    p_organization_id, p_project_id
  );
  IF NOT a1_identity_delivery_reference_only(p_opaque_ref) THEN
    RAISE EXCEPTION 'identity delivery reference is invalid'
      USING ERRCODE = '22023';
  END IF;

  SELECT
    issued.challenge_id,
    issued.accepted,
    issued.retry_after_seconds
    INTO issuance
    FROM a1_issue_identity_verification_challenge(
      p_organization_id,
      p_project_id,
      p_principal_id,
      p_channel,
      p_purpose,
      p_subject_digest,
      p_challenge_digest,
      p_code_digest,
      p_request_context_digest,
      p_expires_at,
      p_max_attempts,
      p_cooldown_seconds,
      p_event_digest,
      p_metadata
    ) AS issued;

  IF issuance.accepted IS TRUE THEN
    UPDATE identity_verification_delivery_outbox AS delivery
       SET id = issuance.challenge_id,
           opaque_ref = p_opaque_ref,
           updated_at = clock_timestamp()
     WHERE delivery.organization_id = p_organization_id
       AND delivery.project_id = p_project_id
       AND delivery.challenge_id = issuance.challenge_id
       AND delivery.status = 'pending'
       AND delivery.attempt_count = 0
       AND delivery.lease_generation = 0
       AND delivery.provider_acceptance_ref IS NULL
       AND delivery.provider_accepted_at IS NULL
    RETURNING delivery.id INTO updated_outbox_id;

    IF NOT FOUND OR updated_outbox_id <> issuance.challenge_id THEN
      RAISE EXCEPTION 'identity delivery outbox creation failed'
        USING ERRCODE = '55000';
    END IF;
  END IF;

  RETURN QUERY SELECT
    issuance.challenge_id::UUID,
    issuance.accepted::BOOLEAN,
    issuance.retry_after_seconds::INTEGER;
END;
$$;

CREATE OR REPLACE FUNCTION a1_claim_identity_delivery_outbox(
  p_organization_id UUID,
  p_project_id UUID,
  p_lease_owner TEXT,
  p_limit INTEGER DEFAULT 25,
  p_lease_milliseconds BIGINT DEFAULT 30000,
  p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS TABLE (
  outbox_id UUID,
  organization_id UUID,
  project_id UUID,
  challenge_id UUID,
  channel TEXT,
  purpose TEXT,
  opaque_ref TEXT,
  challenge_expires_at TIMESTAMPTZ,
  attempt_count INTEGER,
  max_attempts INTEGER,
  provider_idempotency_key TEXT,
  lease_owner TEXT,
  lease_generation BIGINT,
  lease_expires_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  PERFORM a1_identity_delivery_assert_scope(
    p_organization_id, p_project_id
  );
  IF p_lease_owner IS NULL
     OR length(p_lease_owner) NOT BETWEEN 1 AND 256
     OR p_lease_owner !~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'
     OR p_limit < 1 OR p_limit > 500
     OR p_lease_milliseconds < 100
     OR p_lease_milliseconds > 3600000
     OR p_now IS NULL THEN
    RAISE EXCEPTION 'invalid identity delivery claim request'
      USING ERRCODE = '22023';
  END IF;

  RETURN QUERY
  WITH candidates AS (
    SELECT target.id
      FROM identity_verification_delivery_outbox AS target
      JOIN identity_verification_challenges AS challenge
        ON challenge.organization_id = target.organization_id
       AND challenge.project_id = target.project_id
       AND challenge.id = target.challenge_id
     WHERE target.organization_id = p_organization_id
       AND target.project_id = p_project_id
       AND challenge.status = 'pending'
       AND target.opaque_ref IS NOT NULL
       AND target.provider_acceptance_ref IS NULL
       AND target.provider_accepted_at IS NULL
       AND target.attempt_count < target.max_attempts
       AND (
         (
           target.status IN ('pending', 'retry')
           AND target.next_attempt_at <= p_now
         )
         OR (
           target.status = 'leased'
           AND target.lease_expires_at <= p_now
         )
       )
     ORDER BY target.next_attempt_at, target.created_at, target.id
     FOR UPDATE OF target SKIP LOCKED
     LIMIT p_limit
  ),
  claimed AS (
    UPDATE identity_verification_delivery_outbox AS target
       SET status = 'leased',
           attempt_count = target.attempt_count + 1,
           lease_owner = p_lease_owner,
           lease_generation = target.lease_generation + 1,
           lease_expires_at = p_now + make_interval(
             secs => p_lease_milliseconds::DOUBLE PRECISION / 1000.0
           ),
           last_error_code = NULL,
           updated_at = p_now
      FROM candidates
     WHERE target.organization_id = p_organization_id
       AND target.project_id = p_project_id
       AND target.id = candidates.id
    RETURNING target.*
  )
  SELECT
    claimed.id,
    claimed.organization_id,
    claimed.project_id,
    claimed.challenge_id,
    claimed.channel,
    claimed.purpose,
    claimed.opaque_ref,
    challenge.expires_at,
    claimed.attempt_count,
    claimed.max_attempts,
    claimed.provider_idempotency_key,
    claimed.lease_owner,
    claimed.lease_generation,
    claimed.lease_expires_at
    FROM claimed
    JOIN identity_verification_challenges AS challenge
      ON challenge.organization_id = claimed.organization_id
     AND challenge.project_id = claimed.project_id
     AND challenge.id = claimed.challenge_id;
END;
$$;

CREATE OR REPLACE FUNCTION a1_heartbeat_identity_delivery_outbox(
  p_organization_id UUID,
  p_project_id UUID,
  p_outbox_id UUID,
  p_lease_owner TEXT,
  p_lease_generation BIGINT,
  p_lease_milliseconds BIGINT,
  p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS TIMESTAMPTZ
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  target identity_verification_delivery_outbox%ROWTYPE;
BEGIN
  PERFORM a1_identity_delivery_assert_scope(
    p_organization_id, p_project_id
  );
  IF p_lease_milliseconds < 100
     OR p_lease_milliseconds > 3600000
     OR p_now IS NULL THEN
    RAISE EXCEPTION 'invalid identity delivery heartbeat request'
      USING ERRCODE = '22023';
  END IF;

  SELECT *
    INTO target
    FROM identity_verification_delivery_outbox
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_outbox_id
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity delivery lease lost'
      USING ERRCODE = 'P0001';
  END IF;
  IF target.provider_acceptance_ref IS NOT NULL
     OR target.provider_accepted_at IS NOT NULL THEN
    RAISE EXCEPTION 'identity delivery already accepted by provider'
      USING ERRCODE = 'P0004';
  END IF;
  IF target.status <> 'leased'
     OR target.lease_owner <> p_lease_owner
     OR target.lease_generation <> p_lease_generation THEN
    RAISE EXCEPTION 'identity delivery lease lost'
      USING ERRCODE = 'P0001';
  END IF;
  IF target.lease_expires_at <= p_now THEN
    RAISE EXCEPTION 'identity delivery lease expired'
      USING ERRCODE = 'P0002';
  END IF;

  UPDATE identity_verification_delivery_outbox
     SET lease_expires_at = GREATEST(
           target.lease_expires_at,
           p_now + make_interval(
             secs => p_lease_milliseconds::DOUBLE PRECISION / 1000.0
           )
         ),
         updated_at = p_now
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_outbox_id
     AND status = 'leased'
     AND lease_owner = p_lease_owner
     AND lease_generation = p_lease_generation
     AND lease_expires_at > p_now
  RETURNING lease_expires_at INTO target.lease_expires_at;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity delivery lease lost'
      USING ERRCODE = 'P0001';
  END IF;
  RETURN target.lease_expires_at;
END;
$$;

DROP FUNCTION IF EXISTS a1_complete_identity_delivery_outbox(
  UUID, UUID, UUID, TEXT, BIGINT, TIMESTAMPTZ
);

CREATE OR REPLACE FUNCTION a1_complete_identity_delivery_outbox(
  p_organization_id UUID,
  p_project_id UUID,
  p_outbox_id UUID,
  p_lease_owner TEXT,
  p_lease_generation BIGINT,
  p_provider_acceptance_ref TEXT,
  p_provider_accepted_at TIMESTAMPTZ,
  p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  target identity_verification_delivery_outbox%ROWTYPE;
  challenge_issued_at TIMESTAMPTZ;
  challenge_expires_at TIMESTAMPTZ;
BEGIN
  PERFORM a1_identity_delivery_assert_scope(
    p_organization_id, p_project_id
  );
  IF NOT a1_identity_delivery_public_acceptance_reference(
       p_provider_acceptance_ref
     )
     OR p_provider_accepted_at IS NULL
     OR p_now IS NULL
     OR p_provider_accepted_at > p_now THEN
    RAISE EXCEPTION 'invalid identity delivery provider acceptance'
      USING ERRCODE = '22023';
  END IF;

  SELECT *
    INTO target
    FROM identity_verification_delivery_outbox
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_outbox_id
   FOR UPDATE;
  IF NOT FOUND
     OR target.status <> 'leased'
     OR target.lease_owner <> p_lease_owner
     OR target.lease_generation <> p_lease_generation THEN
    RAISE EXCEPTION 'identity delivery lease lost'
      USING ERRCODE = 'P0001';
  END IF;
  IF target.lease_expires_at <= p_now THEN
    RAISE EXCEPTION 'identity delivery lease expired'
      USING ERRCODE = 'P0002';
  END IF;

  SELECT issued_at, expires_at
    INTO challenge_issued_at, challenge_expires_at
    FROM identity_verification_challenges
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = target.challenge_id
   FOR SHARE;
  IF NOT FOUND
     OR p_provider_accepted_at < challenge_issued_at
     OR p_provider_accepted_at > challenge_expires_at THEN
    RAISE EXCEPTION 'identity delivery provider acceptance outside challenge window'
      USING ERRCODE = 'P0003';
  END IF;

  UPDATE identity_verification_delivery_outbox
     SET status = 'delivered',
         delivered_at = p_now,
         dead_at = NULL,
         provider_acceptance_ref = p_provider_acceptance_ref,
         provider_accepted_at = p_provider_accepted_at,
         lease_owner = NULL,
         lease_expires_at = NULL,
         last_error_code = NULL,
         updated_at = p_now
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_outbox_id
     AND status = 'leased'
     AND lease_owner = p_lease_owner
     AND lease_generation = p_lease_generation
     AND lease_expires_at > p_now
  RETURNING id INTO target.id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity delivery lease lost'
      USING ERRCODE = 'P0001';
  END IF;
  RETURN target.id;
END;
$$;

CREATE OR REPLACE FUNCTION a1_retry_identity_delivery_outbox(
  p_organization_id UUID,
  p_project_id UUID,
  p_outbox_id UUID,
  p_lease_owner TEXT,
  p_lease_generation BIGINT,
  p_error_code TEXT,
  p_available_at TIMESTAMPTZ,
  p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  target identity_verification_delivery_outbox%ROWTYPE;
  challenge_expires_at TIMESTAMPTZ;
BEGIN
  PERFORM a1_identity_delivery_assert_scope(
    p_organization_id, p_project_id
  );
  IF p_error_code IS NULL
     OR p_error_code !~ '^[a-z][a-z0-9_.-]{1,63}$'
     OR p_available_at IS NULL
     OR p_available_at < p_now
     OR p_available_at > p_now + INTERVAL '24 hours' THEN
    RAISE EXCEPTION 'invalid identity delivery retry request'
      USING ERRCODE = '22023';
  END IF;

  SELECT *
    INTO target
    FROM identity_verification_delivery_outbox
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_outbox_id
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity delivery lease lost'
      USING ERRCODE = 'P0001';
  END IF;
  IF target.provider_acceptance_ref IS NOT NULL
     OR target.provider_accepted_at IS NOT NULL THEN
    RAISE EXCEPTION 'identity delivery already accepted by provider'
      USING ERRCODE = 'P0004';
  END IF;
  IF target.status <> 'leased'
     OR target.lease_owner <> p_lease_owner
     OR target.lease_generation <> p_lease_generation THEN
    RAISE EXCEPTION 'identity delivery lease lost'
      USING ERRCODE = 'P0001';
  END IF;
  IF target.lease_expires_at <= p_now THEN
    RAISE EXCEPTION 'identity delivery lease expired'
      USING ERRCODE = 'P0002';
  END IF;
  IF target.attempt_count >= target.max_attempts THEN
    RAISE EXCEPTION 'identity delivery attempts exhausted'
      USING ERRCODE = '23514';
  END IF;

  SELECT expires_at
    INTO challenge_expires_at
    FROM identity_verification_challenges
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = target.challenge_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity delivery lease lost'
      USING ERRCODE = 'P0001';
  END IF;

  UPDATE identity_verification_delivery_outbox
     SET status = 'retry',
         next_attempt_at = LEAST(p_available_at, challenge_expires_at),
         delivered_at = NULL,
         dead_at = NULL,
         provider_acceptance_ref = NULL,
         provider_accepted_at = NULL,
         lease_owner = NULL,
         lease_expires_at = NULL,
         last_error_code = p_error_code,
         updated_at = p_now
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_outbox_id
     AND status = 'leased'
     AND lease_owner = p_lease_owner
     AND lease_generation = p_lease_generation
     AND lease_expires_at > p_now
  RETURNING id INTO target.id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity delivery lease lost'
      USING ERRCODE = 'P0001';
  END IF;
  RETURN target.id;
END;
$$;

CREATE OR REPLACE FUNCTION a1_dead_letter_identity_delivery_outbox(
  p_organization_id UUID,
  p_project_id UUID,
  p_outbox_id UUID,
  p_lease_owner TEXT,
  p_lease_generation BIGINT,
  p_error_code TEXT,
  p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  target identity_verification_delivery_outbox%ROWTYPE;
BEGIN
  PERFORM a1_identity_delivery_assert_scope(
    p_organization_id, p_project_id
  );
  IF p_error_code IS NULL
     OR p_error_code !~ '^[a-z][a-z0-9_.-]{1,63}$' THEN
    RAISE EXCEPTION 'invalid identity delivery dead-letter request'
      USING ERRCODE = '22023';
  END IF;

  SELECT *
    INTO target
    FROM identity_verification_delivery_outbox
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_outbox_id
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity delivery lease lost'
      USING ERRCODE = 'P0001';
  END IF;
  IF target.provider_acceptance_ref IS NOT NULL
     OR target.provider_accepted_at IS NOT NULL THEN
    RAISE EXCEPTION 'identity delivery already accepted by provider'
      USING ERRCODE = 'P0004';
  END IF;
  IF target.status <> 'leased'
     OR target.lease_owner <> p_lease_owner
     OR target.lease_generation <> p_lease_generation THEN
    RAISE EXCEPTION 'identity delivery lease lost'
      USING ERRCODE = 'P0001';
  END IF;
  IF target.lease_expires_at <= p_now THEN
    RAISE EXCEPTION 'identity delivery lease expired'
      USING ERRCODE = 'P0002';
  END IF;

  UPDATE identity_verification_delivery_outbox
     SET status = 'dead',
         delivered_at = NULL,
         dead_at = p_now,
         provider_acceptance_ref = NULL,
         provider_accepted_at = NULL,
         lease_owner = NULL,
         lease_expires_at = NULL,
         last_error_code = p_error_code,
         updated_at = p_now
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_outbox_id
     AND status = 'leased'
     AND lease_owner = p_lease_owner
     AND lease_generation = p_lease_generation
     AND lease_expires_at > p_now
  RETURNING id INTO target.id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity delivery lease lost'
      USING ERRCODE = 'P0001';
  END IF;
  RETURN target.id;
END;
$$;

CREATE OR REPLACE FUNCTION a1_redrive_identity_delivery_outbox(
  p_organization_id UUID,
  p_project_id UUID,
  p_outbox_id UUID,
  p_expected_lease_generation BIGINT,
  p_actor_id TEXT,
  p_reason_code TEXT,
  p_request_id TEXT,
  p_requested_at TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS TABLE (
  outbox_id UUID,
  lease_generation BIGINT,
  audit_id UUID,
  redriven_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  target identity_verification_delivery_outbox%ROWTYPE;
  created_audit_id UUID;
  new_generation BIGINT;
  new_provider_key TEXT;
BEGIN
  PERFORM a1_identity_delivery_assert_scope(
    p_organization_id, p_project_id
  );
  IF p_expected_lease_generation < 1
     OR p_actor_id IS NULL
     OR length(p_actor_id) NOT BETWEEN 1 AND 256
     OR p_actor_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'
     OR p_reason_code IS NULL
     OR p_reason_code !~ '^[a-z][a-z0-9_.-]{1,63}$'
     OR p_request_id IS NULL
     OR length(p_request_id) NOT BETWEEN 1 AND 256
     OR p_request_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'
     OR p_requested_at IS NULL THEN
    RAISE EXCEPTION 'invalid identity delivery redrive request'
      USING ERRCODE = '22023';
  END IF;

  SELECT *
    INTO target
    FROM identity_verification_delivery_outbox
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_outbox_id
   FOR UPDATE;
  IF NOT FOUND
     OR target.status <> 'dead'
     OR target.lease_generation <> p_expected_lease_generation
     OR target.lease_owner IS NOT NULL
     OR target.lease_expires_at IS NOT NULL THEN
    RAISE EXCEPTION 'identity delivery redrive fence lost'
      USING ERRCODE = 'P0001';
  END IF;

  new_generation := target.lease_generation + 1;
  new_provider_key :=
    'identity-delivery:' || target.challenge_id::TEXT || ':' ||
    new_generation::TEXT;

  UPDATE identity_verification_delivery_outbox AS redrive_target
     SET status = 'pending',
         attempt_count = 0,
         lease_generation = new_generation,
         next_attempt_at = p_requested_at,
         delivered_at = NULL,
         dead_at = NULL,
         provider_acceptance_ref = NULL,
         provider_accepted_at = NULL,
         last_error_code = NULL,
         provider_idempotency_key = new_provider_key,
         redriven_at = p_requested_at,
         updated_at = p_requested_at
   WHERE redrive_target.organization_id = p_organization_id
     AND redrive_target.project_id = p_project_id
     AND redrive_target.id = p_outbox_id
     AND redrive_target.status = 'dead'
     AND redrive_target.lease_generation = p_expected_lease_generation
     AND redrive_target.lease_owner IS NULL
     AND redrive_target.lease_expires_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity delivery redrive fence lost'
      USING ERRCODE = 'P0001';
  END IF;

  INSERT INTO identity_verification_delivery_redrive_audit (
    organization_id,
    project_id,
    outbox_id,
    actor_id,
    reason_code,
    request_id,
    previous_lease_generation,
    new_lease_generation,
    provider_idempotency_key,
    redriven_at
  ) VALUES (
    p_organization_id,
    p_project_id,
    p_outbox_id,
    p_actor_id,
    p_reason_code,
    p_request_id,
    p_expected_lease_generation,
    new_generation,
    new_provider_key,
    p_requested_at
  )
  RETURNING id INTO created_audit_id;

  RETURN QUERY SELECT
    p_outbox_id,
    new_generation,
    created_audit_id,
    p_requested_at;
END;
$$;

ALTER TABLE identity_verification_delivery_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_verification_delivery_outbox FORCE ROW LEVEL SECURITY;
ALTER TABLE identity_verification_delivery_redrive_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_verification_delivery_redrive_audit FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS identity_verification_delivery_redrive_scope_access
  ON identity_verification_delivery_redrive_audit;
CREATE POLICY identity_verification_delivery_redrive_scope_access
  ON identity_verification_delivery_redrive_audit
  USING (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
  )
  WITH CHECK (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
  );

REVOKE ALL ON TABLE identity_verification_delivery_outbox FROM PUBLIC;
REVOKE ALL ON TABLE identity_verification_delivery_redrive_audit FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_identity_delivery_reference_only(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_identity_delivery_public_acceptance_reference(TEXT)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_identity_delivery_assign_references() FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_identity_delivery_assert_scope(UUID, UUID)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_issue_identity_verification_challenge(
  UUID, UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TIMESTAMPTZ, INTEGER, INTEGER, TEXT, JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_issue_identity_verification_challenge_with_delivery(
  UUID, UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TIMESTAMPTZ, INTEGER, INTEGER, TEXT, TEXT, JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_claim_identity_delivery_outbox(
  UUID, UUID, TEXT, INTEGER, BIGINT, TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_heartbeat_identity_delivery_outbox(
  UUID, UUID, UUID, TEXT, BIGINT, BIGINT, TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_complete_identity_delivery_outbox(
  UUID, UUID, UUID, TEXT, BIGINT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_retry_identity_delivery_outbox(
  UUID, UUID, UUID, TEXT, BIGINT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_dead_letter_identity_delivery_outbox(
  UUID, UUID, UUID, TEXT, BIGINT, TEXT, TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_redrive_identity_delivery_outbox(
  UUID, UUID, UUID, BIGINT, TEXT, TEXT, TEXT, TIMESTAMPTZ
) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a1_runtime') THEN
    REVOKE ALL ON TABLE identity_verification_delivery_outbox
      FROM a1_runtime;
    REVOKE ALL ON TABLE identity_verification_delivery_redrive_audit
      FROM a1_runtime;
    REVOKE ALL ON FUNCTION a1_issue_identity_verification_challenge(
      UUID, UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
      TIMESTAMPTZ, INTEGER, INTEGER, TEXT, JSONB
    ) FROM a1_runtime;
    GRANT EXECUTE ON FUNCTION
      a1_issue_identity_verification_challenge_with_delivery(
        UUID, UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
        TIMESTAMPTZ, INTEGER, INTEGER, TEXT, TEXT, JSONB
      ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_claim_identity_delivery_outbox(
      UUID, UUID, TEXT, INTEGER, BIGINT, TIMESTAMPTZ
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_heartbeat_identity_delivery_outbox(
      UUID, UUID, UUID, TEXT, BIGINT, BIGINT, TIMESTAMPTZ
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_complete_identity_delivery_outbox(
      UUID, UUID, UUID, TEXT, BIGINT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_retry_identity_delivery_outbox(
      UUID, UUID, UUID, TEXT, BIGINT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_dead_letter_identity_delivery_outbox(
      UUID, UUID, UUID, TEXT, BIGINT, TEXT, TIMESTAMPTZ
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_redrive_identity_delivery_outbox(
      UUID, UUID, UUID, BIGINT, TEXT, TEXT, TEXT, TIMESTAMPTZ
    ) TO a1_runtime;
  END IF;
END;
$$;

COMMIT;
