-- Durable, digest-only identity verification for tenant/project runtimes.
-- Raw OTP values and destination identifiers must be normalized and digested
-- before crossing this PostgreSQL boundary.
-- The transactional contract's identifier_digest is represented by the
-- canonical subject_digest used consistently by credentials and proofs.

BEGIN;

CREATE TABLE IF NOT EXISTS identity_verification_cooldowns (
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  channel TEXT NOT NULL CHECK (channel IN ('email', 'phone')),
  purpose TEXT NOT NULL CHECK (
    purpose IN ('login', 'credential_binding', 'account_recovery', 'step_up')
  ),
  subject_digest TEXT NOT NULL CHECK (
    a1_identity_digest_valid(subject_digest)
  ),
  last_issued_at TIMESTAMPTZ,
  next_allowed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  consecutive_failures INTEGER NOT NULL DEFAULT 0
    CHECK (consecutive_failures BETWEEN 0 AND 1000),
  blocked_until TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (
    organization_id, project_id, channel, purpose, subject_digest
  ),
  CONSTRAINT identity_verification_cooldowns_project_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT identity_verification_cooldowns_block_check CHECK (
    blocked_until IS NULL OR blocked_until >= next_allowed_at
  )
);

CREATE TABLE IF NOT EXISTS identity_verification_challenges (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  principal_id UUID,
  channel TEXT NOT NULL CHECK (channel IN ('email', 'phone')),
  purpose TEXT NOT NULL CHECK (
    purpose IN ('login', 'credential_binding', 'account_recovery', 'step_up')
  ),
  subject_digest TEXT NOT NULL CHECK (
    a1_identity_digest_valid(subject_digest)
  ),
  challenge_digest TEXT NOT NULL CHECK (
    a1_identity_digest_valid(challenge_digest)
  ),
  code_digest TEXT NOT NULL CHECK (a1_identity_digest_valid(code_digest)),
  request_context_digest TEXT NOT NULL CHECK (
    a1_identity_digest_valid(request_context_digest)
  ),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (
    status IN ('pending', 'consumed', 'expired', 'locked', 'revoked', 'verified')
  ),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  max_attempts INTEGER NOT NULL DEFAULT 5 CHECK (
    max_attempts BETWEEN 1 AND 10
  ),
  issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  verified_at TIMESTAMPTZ,
  consumed_at TIMESTAMPTZ,
  locked_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (
    a1_identity_public_metadata(metadata)
  ),
  CONSTRAINT identity_verification_challenges_digest_key
    UNIQUE (challenge_digest),
  CONSTRAINT identity_verification_challenges_scope_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT identity_verification_challenges_project_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT identity_verification_challenges_principal_fk
    FOREIGN KEY (principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT identity_verification_challenges_principal_purpose_check CHECK (
    purpose = 'login' OR principal_id IS NOT NULL
  ),
  CONSTRAINT identity_verification_challenges_ttl_check CHECK (
    expires_at > issued_at
    AND expires_at <= issued_at + INTERVAL '15 minutes'
  ),
  CONSTRAINT identity_verification_challenges_attempt_check CHECK (
    attempt_count <= max_attempts
  ),
  CONSTRAINT identity_verification_challenges_state_check CHECK (
    (
      status = 'pending'
      AND verified_at IS NULL
      AND consumed_at IS NULL
      AND locked_at IS NULL
      AND revoked_at IS NULL
    )
    OR (
      status = 'consumed'
      AND verified_at IS NOT NULL
      AND consumed_at IS NOT NULL
      AND locked_at IS NULL
      AND revoked_at IS NULL
    )
    OR (
      status = 'verified'
      AND verified_at IS NOT NULL
      AND consumed_at IS NULL
      AND locked_at IS NULL
      AND revoked_at IS NULL
    )
    OR (
      status = 'locked'
      AND locked_at IS NOT NULL
      AND verified_at IS NULL
      AND consumed_at IS NULL
      AND revoked_at IS NULL
    )
    OR (
      status = 'revoked'
      AND revoked_at IS NOT NULL
      AND verified_at IS NULL
      AND consumed_at IS NULL
      AND locked_at IS NULL
    )
    OR (
      status = 'expired'
      AND verified_at IS NULL
      AND consumed_at IS NULL
      AND locked_at IS NULL
      AND revoked_at IS NULL
    )
  )
);

CREATE INDEX IF NOT EXISTS identity_verification_challenges_pending_idx
  ON identity_verification_challenges(
    organization_id, project_id, channel, purpose, expires_at
  )
  WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS identity_verification_challenges_principal_idx
  ON identity_verification_challenges(
    principal_id, organization_id, project_id, issued_at DESC
  )
  WHERE principal_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS identity_verification_receipts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  challenge_id UUID NOT NULL,
  principal_id UUID,
  channel TEXT NOT NULL CHECK (channel IN ('email', 'phone')),
  purpose TEXT NOT NULL CHECK (
    purpose IN ('login', 'credential_binding', 'account_recovery', 'step_up')
  ),
  subject_digest TEXT NOT NULL CHECK (
    a1_identity_digest_valid(subject_digest)
  ),
  request_context_digest TEXT NOT NULL CHECK (
    a1_identity_digest_valid(request_context_digest)
  ),
  receipt_digest TEXT NOT NULL CHECK (
    a1_identity_digest_valid(receipt_digest)
  ),
  status TEXT NOT NULL DEFAULT 'verified' CHECK (
    status IN ('verified', 'consumed', 'expired', 'revoked')
  ),
  verified_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  idempotency_digest TEXT CHECK (
    idempotency_digest IS NULL
    OR a1_identity_digest_valid(idempotency_digest)
  ),
  request_digest TEXT CHECK (
    request_digest IS NULL OR a1_identity_digest_valid(request_digest)
  ),
  mutation_kind TEXT CHECK (
    mutation_kind IS NULL OR mutation_kind IN ('bind', 'login', 'recovery')
  ),
  mutation_result_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT identity_verification_receipts_challenge_key
    UNIQUE (challenge_id),
  CONSTRAINT identity_verification_receipts_digest_key
    UNIQUE (receipt_digest),
  CONSTRAINT identity_verification_receipts_idempotency_key
    UNIQUE (organization_id, project_id, idempotency_digest),
  CONSTRAINT identity_verification_receipts_challenge_scope_fk
    FOREIGN KEY (organization_id, project_id, challenge_id)
    REFERENCES identity_verification_challenges(
      organization_id, project_id, id
    ) ON DELETE RESTRICT,
  CONSTRAINT identity_verification_receipts_principal_fk
    FOREIGN KEY (principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT identity_verification_receipts_state_check CHECK (
    (
      status = 'verified'
      AND consumed_at IS NULL
      AND idempotency_digest IS NULL
      AND request_digest IS NULL
      AND mutation_kind IS NULL
      AND mutation_result_id IS NULL
    )
    OR (
      status = 'consumed'
      AND consumed_at IS NOT NULL
      AND idempotency_digest IS NOT NULL
      AND request_digest IS NOT NULL
      AND mutation_kind IS NOT NULL
      AND mutation_result_id IS NOT NULL
    )
    OR (
      status IN ('expired', 'revoked')
      AND consumed_at IS NULL
      AND mutation_result_id IS NULL
    )
  )
);

CREATE INDEX IF NOT EXISTS identity_verification_receipts_scope_created_idx
  ON identity_verification_receipts(
    organization_id, project_id, created_at DESC
  );

CREATE TABLE IF NOT EXISTS identity_verification_delivery_outbox (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  challenge_id UUID NOT NULL,
  channel TEXT NOT NULL CHECK (channel IN ('email', 'phone')),
  purpose TEXT NOT NULL CHECK (
    purpose IN ('login', 'credential_binding', 'account_recovery', 'step_up')
  ),
  subject_digest TEXT NOT NULL CHECK (
    a1_identity_digest_valid(subject_digest)
  ),
  delivery_digest TEXT NOT NULL CHECK (
    a1_identity_digest_valid(delivery_digest)
  ),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (
    status IN ('pending', 'leased', 'delivered', 'retry', 'dead')
  ),
  lease_owner TEXT,
  lease_generation BIGINT NOT NULL DEFAULT 0 CHECK (lease_generation >= 0),
  lease_expires_at TIMESTAMPTZ,
  attempt_count INTEGER NOT NULL DEFAULT 0
    CHECK (attempt_count BETWEEN 0 AND 1000),
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  delivered_at TIMESTAMPTZ,
  dead_at TIMESTAMPTZ,
  last_error_digest TEXT CHECK (
    last_error_digest IS NULL OR a1_identity_digest_valid(last_error_digest)
  ),
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (
    a1_identity_public_metadata(metadata)
  ),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT identity_verification_delivery_outbox_challenge_key
    UNIQUE (challenge_id),
  CONSTRAINT identity_verification_delivery_outbox_digest_key
    UNIQUE (delivery_digest),
  CONSTRAINT identity_verification_delivery_outbox_challenge_scope_fk
    FOREIGN KEY (organization_id, project_id, challenge_id)
    REFERENCES identity_verification_challenges(
      organization_id, project_id, id
    ) ON DELETE RESTRICT,
  CONSTRAINT identity_verification_delivery_outbox_lease_check CHECK (
    (status = 'leased' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
    OR status <> 'leased'
  ),
  CONSTRAINT identity_verification_delivery_outbox_terminal_check CHECK (
    (status = 'delivered' AND delivered_at IS NOT NULL)
    OR (status = 'dead' AND dead_at IS NOT NULL)
    OR status NOT IN ('delivered', 'dead')
  )
);

CREATE INDEX IF NOT EXISTS identity_verification_delivery_ready_idx
  ON identity_verification_delivery_outbox(
    organization_id, project_id, next_attempt_at, created_at
  )
  WHERE status IN ('pending', 'retry');

CREATE TABLE IF NOT EXISTS identity_verification_abuse_budgets (
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  channel TEXT NOT NULL CHECK (channel IN ('email', 'phone')),
  purpose TEXT NOT NULL CHECK (
    purpose IN ('login', 'credential_binding', 'account_recovery', 'step_up')
  ),
  subject_digest TEXT NOT NULL CHECK (
    a1_identity_digest_valid(subject_digest)
  ),
  window_started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  issue_count INTEGER NOT NULL DEFAULT 0 CHECK (issue_count >= 0),
  verify_failure_count INTEGER NOT NULL DEFAULT 0
    CHECK (verify_failure_count >= 0),
  delivery_failure_count INTEGER NOT NULL DEFAULT 0
    CHECK (delivery_failure_count >= 0),
  blocked_until TIMESTAMPTZ,
  last_event_digest TEXT CHECK (
    last_event_digest IS NULL OR a1_identity_digest_valid(last_event_digest)
  ),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (
    organization_id, project_id, channel, purpose, subject_digest
  ),
  CONSTRAINT identity_verification_abuse_budgets_project_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS identity_verification_audit_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  challenge_id UUID,
  principal_id UUID,
  event_type TEXT NOT NULL CHECK (
    event_type IN (
      'challenge_issued',
      'challenge_rejected',
      'challenge_locked',
      'challenge_expired',
      'challenge_consumed',
      'proof_verified',
      'credential_bound',
      'login_succeeded',
      'recovery_succeeded',
      'delivery_failed'
    )
  ),
  outcome_code TEXT NOT NULL CHECK (
    outcome_code IN (
      'issued',
      'cooldown_active',
      'context_mismatch',
      'proof_mismatch',
      'attempts_exhausted',
      'expired',
      'consumed',
      'verified',
      'bound',
      'authenticated',
      'recovered',
      'idempotency_conflict',
      'delivery_failed'
    )
  ),
  attempt_number INTEGER NOT NULL DEFAULT 0 CHECK (attempt_number >= 0),
  request_context_digest TEXT NOT NULL CHECK (
    a1_identity_digest_valid(request_context_digest)
  ),
  event_digest TEXT NOT NULL CHECK (
    a1_identity_digest_valid(event_digest)
  ),
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (
    a1_identity_public_metadata(metadata)
  ),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT identity_verification_audit_events_digest_key
    UNIQUE (event_digest),
  CONSTRAINT identity_verification_audit_events_challenge_scope_fk
    FOREIGN KEY (organization_id, project_id, challenge_id)
    REFERENCES identity_verification_challenges(
      organization_id, project_id, id
    ) ON DELETE RESTRICT,
  CONSTRAINT identity_verification_audit_events_principal_fk
    FOREIGN KEY (principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS identity_verification_audit_scope_created_idx
  ON identity_verification_audit_events(
    organization_id, project_id, created_at DESC
  );

CREATE OR REPLACE FUNCTION a1_identity_verification_assert_scope(
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
  PERFORM a1_assert_role_nobypassrls(session_user);

  IF p_organization_id IS NULL
     OR p_project_id IS NULL
     OR p_organization_id IS DISTINCT FROM a1_current_organization_id()
     OR p_project_id IS DISTINCT FROM a1_current_project_id() THEN
    RAISE EXCEPTION 'identity verification scope is unavailable'
      USING ERRCODE = '42501';
  END IF;

  IF NOT EXISTS (
    SELECT 1
      FROM projects AS project
      JOIN organizations AS organization
        ON organization.id = project.organization_id
     WHERE project.organization_id = p_organization_id
       AND project.id = p_project_id
       AND project.status = 'active'
       AND organization.status = 'active'
  ) THEN
    RAISE EXCEPTION 'identity verification scope is unavailable'
      USING ERRCODE = '42501';
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION a1_issue_identity_verification_challenge(
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
  v_now TIMESTAMPTZ := clock_timestamp();
  cooldown identity_verification_cooldowns%ROWTYPE;
  created_challenge_id UUID;
BEGIN
  PERFORM a1_identity_verification_assert_scope(
    p_organization_id, p_project_id
  );

  IF p_channel NOT IN ('email', 'phone')
     OR p_purpose NOT IN (
       'login', 'credential_binding', 'account_recovery', 'step_up'
     )
     OR (p_purpose <> 'login' AND p_principal_id IS NULL)
     OR NOT a1_identity_digest_valid(p_subject_digest)
     OR NOT a1_identity_digest_valid(p_challenge_digest)
     OR NOT a1_identity_digest_valid(p_code_digest)
     OR NOT a1_identity_digest_valid(p_request_context_digest)
     OR NOT a1_identity_digest_valid(p_event_digest)
     OR NOT a1_identity_public_metadata(p_metadata)
     OR p_expires_at <= v_now
     OR p_expires_at > v_now + INTERVAL '15 minutes'
     OR p_max_attempts NOT BETWEEN 1 AND 10
     OR p_cooldown_seconds NOT BETWEEN 1 AND 3600 THEN
    RAISE EXCEPTION 'identity verification request is invalid'
      USING ERRCODE = '22023';
  END IF;

  IF p_principal_id IS NOT NULL AND NOT EXISTS (
    SELECT 1
      FROM identity_principals AS principal
      JOIN identity_organization_memberships AS organization_membership
        ON organization_membership.principal_id = principal.id
       AND organization_membership.organization_id = p_organization_id
       AND organization_membership.status = 'active'
      JOIN identity_project_memberships AS project_membership
        ON project_membership.organization_id = p_organization_id
       AND project_membership.project_id = p_project_id
       AND project_membership.principal_id = principal.id
       AND project_membership.organization_membership_id =
             organization_membership.id
       AND project_membership.status = 'active'
     WHERE principal.id = p_principal_id
       AND principal.status = 'active'
  ) THEN
    RAISE EXCEPTION 'identity verification principal is unavailable'
      USING ERRCODE = '42501';
  END IF;

  PERFORM pg_advisory_xact_lock(
    hashtextextended(
      p_organization_id::TEXT || ':' ||
      p_project_id::TEXT || ':' ||
      p_channel || ':' ||
      p_purpose || ':' ||
      p_subject_digest,
      0
    )
  );

  SELECT *
    INTO cooldown
    FROM identity_verification_cooldowns
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND channel = p_channel
     AND purpose = p_purpose
     AND subject_digest = p_subject_digest
   FOR UPDATE;

  IF FOUND AND (
    cooldown.next_allowed_at > v_now
    OR cooldown.blocked_until > v_now
  ) THEN
    RETURN QUERY SELECT
      NULL::UUID,
      FALSE,
      greatest(
        1,
        ceil(
          extract(
            epoch FROM (
              greatest(
                cooldown.next_allowed_at,
                COALESCE(cooldown.blocked_until, cooldown.next_allowed_at)
              ) - v_now
            )
          )
        )::INTEGER
      );
    RETURN;
  END IF;

  UPDATE identity_verification_challenges
     SET status = 'revoked',
         revoked_at = v_now
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND channel = p_channel
     AND purpose = p_purpose
     AND subject_digest = p_subject_digest
     AND status = 'pending';

  INSERT INTO identity_verification_challenges (
    organization_id,
    project_id,
    principal_id,
    channel,
    purpose,
    subject_digest,
    challenge_digest,
    code_digest,
    request_context_digest,
    max_attempts,
    issued_at,
    expires_at,
    metadata
  ) VALUES (
    p_organization_id,
    p_project_id,
    p_principal_id,
    p_channel,
    p_purpose,
    p_subject_digest,
    p_challenge_digest,
    p_code_digest,
    p_request_context_digest,
    p_max_attempts,
    v_now,
    p_expires_at,
    p_metadata
  )
  RETURNING id INTO created_challenge_id;

  INSERT INTO identity_verification_delivery_outbox (
    organization_id,
    project_id,
    challenge_id,
    channel,
    purpose,
    subject_digest,
    delivery_digest,
    next_attempt_at,
    metadata
  ) VALUES (
    p_organization_id,
    p_project_id,
    created_challenge_id,
    p_channel,
    p_purpose,
    p_subject_digest,
    p_event_digest,
    v_now,
    p_metadata
  );

  INSERT INTO identity_verification_abuse_budgets (
    organization_id,
    project_id,
    channel,
    purpose,
    subject_digest,
    window_started_at,
    issue_count,
    last_event_digest,
    updated_at
  ) VALUES (
    p_organization_id,
    p_project_id,
    p_channel,
    p_purpose,
    p_subject_digest,
    v_now,
    1,
    p_event_digest,
    v_now
  )
  ON CONFLICT (
    organization_id, project_id, channel, purpose, subject_digest
  ) DO UPDATE SET
    window_started_at = CASE
      WHEN identity_verification_abuse_budgets.window_started_at
           <= v_now - INTERVAL '1 hour'
        THEN v_now
      ELSE identity_verification_abuse_budgets.window_started_at
    END,
    issue_count = CASE
      WHEN identity_verification_abuse_budgets.window_started_at
           <= v_now - INTERVAL '1 hour'
        THEN 1
      ELSE identity_verification_abuse_budgets.issue_count + 1
    END,
    last_event_digest = EXCLUDED.last_event_digest,
    updated_at = EXCLUDED.updated_at;

  INSERT INTO identity_verification_cooldowns (
    organization_id,
    project_id,
    channel,
    purpose,
    subject_digest,
    last_issued_at,
    next_allowed_at,
    consecutive_failures,
    blocked_until,
    updated_at
  ) VALUES (
    p_organization_id,
    p_project_id,
    p_channel,
    p_purpose,
    p_subject_digest,
    v_now,
    v_now + make_interval(secs => p_cooldown_seconds),
    0,
    NULL,
    v_now
  )
  ON CONFLICT (
    organization_id, project_id, channel, purpose, subject_digest
  ) DO UPDATE SET
    last_issued_at = EXCLUDED.last_issued_at,
    next_allowed_at = EXCLUDED.next_allowed_at,
    consecutive_failures = 0,
    blocked_until = NULL,
    updated_at = EXCLUDED.updated_at;

  INSERT INTO identity_verification_audit_events (
    organization_id,
    project_id,
    challenge_id,
    principal_id,
    event_type,
    outcome_code,
    attempt_number,
    request_context_digest,
    event_digest,
    metadata
  ) VALUES (
    p_organization_id,
    p_project_id,
    created_challenge_id,
    p_principal_id,
    'challenge_issued',
    'issued',
    0,
    p_request_context_digest,
    p_event_digest,
    p_metadata
  );

  RETURN QUERY SELECT created_challenge_id, TRUE, 0;
END;
$$;

CREATE OR REPLACE FUNCTION a1_verify_consume_identity_challenge(
  p_organization_id UUID,
  p_project_id UUID,
  p_challenge_digest TEXT,
  p_candidate_code_digest TEXT,
  p_request_context_digest TEXT,
  p_receipt_digest TEXT,
  p_event_digest TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE (
  outcome_code TEXT,
  challenge_id UUID,
  receipt_id UUID,
  principal_id UUID,
  channel TEXT,
  purpose TEXT,
  attempts_remaining INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_now TIMESTAMPTZ := clock_timestamp();
  challenge identity_verification_challenges%ROWTYPE;
  created_receipt_id UUID;
  next_attempt INTEGER;
  failure_code TEXT;
  lock_seconds INTEGER;
BEGIN
  PERFORM a1_identity_verification_assert_scope(
    p_organization_id, p_project_id
  );

  IF NOT a1_identity_digest_valid(p_challenge_digest)
     OR NOT a1_identity_digest_valid(p_candidate_code_digest)
     OR NOT a1_identity_digest_valid(p_request_context_digest)
     OR NOT a1_identity_digest_valid(p_receipt_digest)
     OR NOT a1_identity_digest_valid(p_event_digest)
     OR NOT a1_identity_public_metadata(p_metadata) THEN
    RAISE EXCEPTION 'identity verification request is invalid'
      USING ERRCODE = '22023';
  END IF;

  SELECT *
    INTO challenge
    FROM identity_verification_challenges
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND challenge_digest = p_challenge_digest
   FOR UPDATE;

  IF NOT FOUND THEN
    RETURN QUERY SELECT
      'rejected'::TEXT,
      NULL::UUID,
      NULL::UUID,
      NULL::UUID,
      NULL::TEXT,
      NULL::TEXT,
      0;
    RETURN;
  END IF;

  IF challenge.status <> 'pending' THEN
    RETURN QUERY SELECT
      'rejected'::TEXT,
      challenge.id,
      NULL::UUID,
      challenge.principal_id,
      challenge.channel,
      challenge.purpose,
      greatest(0, challenge.max_attempts - challenge.attempt_count);
    RETURN;
  END IF;

  IF challenge.expires_at <= v_now THEN
    UPDATE identity_verification_challenges
       SET status = 'expired'
     WHERE id = challenge.id;

    INSERT INTO identity_verification_audit_events (
      organization_id, project_id, challenge_id, principal_id,
      event_type, outcome_code, attempt_number,
      request_context_digest, event_digest, metadata
    ) VALUES (
      challenge.organization_id, challenge.project_id, challenge.id,
      challenge.principal_id, 'challenge_expired', 'expired',
      challenge.attempt_count, p_request_context_digest, p_event_digest,
      p_metadata
    );

    RETURN QUERY SELECT
      'rejected'::TEXT,
      challenge.id,
      NULL::UUID,
      challenge.principal_id,
      challenge.channel,
      challenge.purpose,
      greatest(0, challenge.max_attempts - challenge.attempt_count);
    RETURN;
  END IF;

  IF challenge.request_context_digest <> p_request_context_digest THEN
    failure_code := 'context_mismatch';
  ELSIF digest(challenge.code_digest, 'sha256') <>
        digest(p_candidate_code_digest, 'sha256') THEN
    failure_code := 'proof_mismatch';
  END IF;

  IF failure_code IS NOT NULL THEN
    next_attempt := challenge.attempt_count + 1;
    lock_seconds := least(3600, 30 * (2 ^ least(next_attempt - 1, 6)));

    UPDATE identity_verification_challenges
       SET attempt_count = next_attempt,
           status = CASE
             WHEN next_attempt >= challenge.max_attempts THEN 'locked'
             ELSE 'pending'
           END,
           locked_at = CASE
             WHEN next_attempt >= challenge.max_attempts THEN v_now
             ELSE NULL
           END
     WHERE id = challenge.id;

    INSERT INTO identity_verification_cooldowns (
      organization_id, project_id, channel, purpose, subject_digest,
      next_allowed_at, consecutive_failures, blocked_until, updated_at
    ) VALUES (
      challenge.organization_id, challenge.project_id, challenge.channel,
      challenge.purpose, challenge.subject_digest,
      v_now + make_interval(secs => lock_seconds),
      1,
      CASE
        WHEN next_attempt >= challenge.max_attempts
          THEN v_now + INTERVAL '1 hour'
        ELSE NULL
      END,
      v_now
    )
    ON CONFLICT ON CONSTRAINT identity_verification_cooldowns_pkey
    DO UPDATE SET
      next_allowed_at = greatest(
        identity_verification_cooldowns.next_allowed_at,
        EXCLUDED.next_allowed_at
      ),
      consecutive_failures = least(
        1000,
        identity_verification_cooldowns.consecutive_failures + 1
      ),
      blocked_until = CASE
        WHEN next_attempt >= challenge.max_attempts THEN greatest(
          COALESCE(
            identity_verification_cooldowns.blocked_until,
            EXCLUDED.blocked_until
          ),
          EXCLUDED.blocked_until
        )
        ELSE identity_verification_cooldowns.blocked_until
      END,
      updated_at = EXCLUDED.updated_at;

    INSERT INTO identity_verification_audit_events (
      organization_id, project_id, challenge_id, principal_id,
      event_type, outcome_code, attempt_number,
      request_context_digest, event_digest, metadata
    ) VALUES (
      challenge.organization_id, challenge.project_id, challenge.id,
      challenge.principal_id,
      CASE
        WHEN next_attempt >= challenge.max_attempts
          THEN 'challenge_locked'
        ELSE 'challenge_rejected'
      END,
      CASE
        WHEN next_attempt >= challenge.max_attempts
          THEN 'attempts_exhausted'
        ELSE failure_code
      END,
      next_attempt, p_request_context_digest, p_event_digest, p_metadata
    );

    RETURN QUERY SELECT
      'rejected'::TEXT,
      challenge.id,
      NULL::UUID,
      challenge.principal_id,
      challenge.channel,
      challenge.purpose,
      greatest(0, challenge.max_attempts - next_attempt);
    RETURN;
  END IF;

  UPDATE identity_verification_challenges
     SET status = 'consumed',
         verified_at = v_now,
         consumed_at = v_now
   WHERE id = challenge.id
     AND status = 'pending';

  INSERT INTO identity_verification_receipts (
    organization_id,
    project_id,
    challenge_id,
    principal_id,
    channel,
    purpose,
    subject_digest,
    request_context_digest,
    receipt_digest,
    status,
    verified_at,
    consumed_at,
    idempotency_digest,
    request_digest,
    mutation_kind,
    mutation_result_id
  ) VALUES (
    challenge.organization_id,
    challenge.project_id,
    challenge.id,
    challenge.principal_id,
    challenge.channel,
    challenge.purpose,
    challenge.subject_digest,
    p_request_context_digest,
    p_receipt_digest,
    'consumed',
    v_now,
    v_now,
    p_receipt_digest,
    p_request_context_digest,
    'login',
    challenge.id
  )
  RETURNING id INTO created_receipt_id;

  UPDATE identity_verification_cooldowns AS cooldown
     SET consecutive_failures = 0,
         blocked_until = NULL,
         updated_at = v_now
   WHERE cooldown.organization_id = challenge.organization_id
     AND cooldown.project_id = challenge.project_id
     AND cooldown.channel = challenge.channel
     AND cooldown.purpose = challenge.purpose
     AND cooldown.subject_digest = challenge.subject_digest;

  INSERT INTO identity_verification_audit_events (
    organization_id, project_id, challenge_id, principal_id,
    event_type, outcome_code, attempt_number,
    request_context_digest, event_digest, metadata
  ) VALUES (
    challenge.organization_id, challenge.project_id, challenge.id,
    challenge.principal_id, 'challenge_consumed', 'consumed',
    challenge.attempt_count, p_request_context_digest, p_event_digest,
    p_metadata
  );

  RETURN QUERY SELECT
    'consumed'::TEXT,
    challenge.id,
    created_receipt_id,
    challenge.principal_id,
    challenge.channel,
    challenge.purpose,
    challenge.max_attempts - challenge.attempt_count;
END;
$$;

CREATE OR REPLACE FUNCTION a1_verify_identity_verification_attempt(
  p_organization_id UUID,
  p_project_id UUID,
  p_challenge_digest TEXT,
  p_candidate_code_digest TEXT,
  p_request_context_digest TEXT,
  p_receipt_digest TEXT,
  p_event_digest TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE (
  outcome_code TEXT,
  challenge_id UUID,
  receipt_id UUID,
  principal_id UUID,
  channel TEXT,
  purpose TEXT,
  attempts_remaining INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_now TIMESTAMPTZ := clock_timestamp();
  challenge identity_verification_challenges%ROWTYPE;
  created_receipt_id UUID;
  next_attempt INTEGER;
  failure_code TEXT;
  lock_seconds INTEGER;
BEGIN
  PERFORM a1_identity_verification_assert_scope(
    p_organization_id, p_project_id
  );

  IF NOT a1_identity_digest_valid(p_challenge_digest)
     OR NOT a1_identity_digest_valid(p_candidate_code_digest)
     OR NOT a1_identity_digest_valid(p_request_context_digest)
     OR NOT a1_identity_digest_valid(p_receipt_digest)
     OR NOT a1_identity_digest_valid(p_event_digest)
     OR NOT a1_identity_public_metadata(p_metadata) THEN
    RAISE EXCEPTION 'identity verification request is invalid'
      USING ERRCODE = '22023';
  END IF;

  SELECT *
    INTO challenge
    FROM identity_verification_challenges
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND challenge_digest = p_challenge_digest
   FOR UPDATE;

  IF NOT FOUND OR challenge.status <> 'pending' THEN
    RETURN QUERY SELECT
      'rejected'::TEXT,
      challenge.id,
      NULL::UUID,
      challenge.principal_id,
      challenge.channel,
      challenge.purpose,
      COALESCE(greatest(
        0, challenge.max_attempts - challenge.attempt_count
      ), 0);
    RETURN;
  END IF;

  IF challenge.expires_at <= v_now THEN
    UPDATE identity_verification_challenges
       SET status = 'expired'
     WHERE id = challenge.id;
    failure_code := 'expired';
  ELSIF challenge.request_context_digest <> p_request_context_digest THEN
    failure_code := 'context_mismatch';
  ELSIF digest(challenge.code_digest, 'sha256') <>
        digest(p_candidate_code_digest, 'sha256') THEN
    failure_code := 'proof_mismatch';
  END IF;

  IF failure_code IS NOT NULL THEN
    IF failure_code = 'expired' THEN
      next_attempt := challenge.attempt_count;
    ELSE
      next_attempt := challenge.attempt_count + 1;
      lock_seconds := least(3600, 30 * (2 ^ least(next_attempt - 1, 6)));

      UPDATE identity_verification_challenges
         SET attempt_count = next_attempt,
             status = CASE
               WHEN next_attempt >= challenge.max_attempts THEN 'locked'
               ELSE 'pending'
             END,
             locked_at = CASE
               WHEN next_attempt >= challenge.max_attempts THEN v_now
               ELSE NULL
             END
       WHERE id = challenge.id;

      INSERT INTO identity_verification_abuse_budgets (
        organization_id, project_id, channel, purpose, subject_digest,
        verify_failure_count, blocked_until, last_event_digest, updated_at
      ) VALUES (
        challenge.organization_id, challenge.project_id, challenge.channel,
        challenge.purpose, challenge.subject_digest, 1,
        CASE WHEN next_attempt >= challenge.max_attempts
          THEN v_now + INTERVAL '1 hour' ELSE NULL END,
        p_event_digest, v_now
      )
      ON CONFLICT (
        organization_id, project_id, channel, purpose, subject_digest
      ) DO UPDATE SET
        verify_failure_count =
          identity_verification_abuse_budgets.verify_failure_count + 1,
        blocked_until = CASE
          WHEN next_attempt >= challenge.max_attempts THEN greatest(
            COALESCE(
              identity_verification_abuse_budgets.blocked_until,
              EXCLUDED.blocked_until
            ),
            EXCLUDED.blocked_until
          )
          ELSE identity_verification_abuse_budgets.blocked_until
        END,
        last_event_digest = EXCLUDED.last_event_digest,
        updated_at = EXCLUDED.updated_at;

      UPDATE identity_verification_cooldowns AS cooldown
         SET next_allowed_at = greatest(
               cooldown.next_allowed_at,
               v_now + make_interval(secs => lock_seconds)
             ),
             consecutive_failures = least(
               1000, cooldown.consecutive_failures + 1
             ),
             blocked_until = CASE
               WHEN next_attempt >= challenge.max_attempts
                 THEN v_now + INTERVAL '1 hour'
               ELSE cooldown.blocked_until
             END,
             updated_at = v_now
       WHERE cooldown.organization_id = challenge.organization_id
         AND cooldown.project_id = challenge.project_id
         AND cooldown.channel = challenge.channel
         AND cooldown.purpose = challenge.purpose
         AND cooldown.subject_digest = challenge.subject_digest;
    END IF;

    INSERT INTO identity_verification_audit_events (
      organization_id, project_id, challenge_id, principal_id,
      event_type, outcome_code, attempt_number,
      request_context_digest, event_digest, metadata
    ) VALUES (
      challenge.organization_id, challenge.project_id, challenge.id,
      challenge.principal_id,
      CASE
        WHEN failure_code = 'expired' THEN 'challenge_expired'
        WHEN next_attempt >= challenge.max_attempts THEN 'challenge_locked'
        ELSE 'challenge_rejected'
      END,
      CASE
        WHEN next_attempt >= challenge.max_attempts
             AND failure_code <> 'expired' THEN 'attempts_exhausted'
        ELSE failure_code
      END,
      next_attempt, p_request_context_digest, p_event_digest, p_metadata
    );

    RETURN QUERY SELECT
      'rejected'::TEXT, challenge.id, NULL::UUID,
      challenge.principal_id, challenge.channel, challenge.purpose,
      greatest(0, challenge.max_attempts - next_attempt);
    RETURN;
  END IF;

  UPDATE identity_verification_challenges
     SET status = 'verified',
         verified_at = v_now
   WHERE id = challenge.id
     AND status = 'pending';

  INSERT INTO identity_verification_receipts (
    organization_id, project_id, challenge_id, principal_id,
    channel, purpose, subject_digest, request_context_digest,
    receipt_digest, status, verified_at
  ) VALUES (
    challenge.organization_id, challenge.project_id, challenge.id,
    challenge.principal_id, challenge.channel, challenge.purpose,
    challenge.subject_digest, p_request_context_digest,
    p_receipt_digest, 'verified', v_now
  )
  RETURNING id INTO created_receipt_id;

  UPDATE identity_verification_cooldowns AS cooldown
     SET consecutive_failures = 0,
         blocked_until = NULL,
         updated_at = v_now
   WHERE cooldown.organization_id = challenge.organization_id
     AND cooldown.project_id = challenge.project_id
     AND cooldown.channel = challenge.channel
     AND cooldown.purpose = challenge.purpose
     AND cooldown.subject_digest = challenge.subject_digest;

  INSERT INTO identity_verification_audit_events (
    organization_id, project_id, challenge_id, principal_id,
    event_type, outcome_code, attempt_number,
    request_context_digest, event_digest, metadata
  ) VALUES (
    challenge.organization_id, challenge.project_id, challenge.id,
    challenge.principal_id, 'proof_verified', 'verified',
    challenge.attempt_count, p_request_context_digest, p_event_digest,
    p_metadata
  );

  RETURN QUERY SELECT
    'verified'::TEXT, challenge.id, created_receipt_id,
    challenge.principal_id, challenge.channel, challenge.purpose,
    challenge.max_attempts - challenge.attempt_count;
END;
$$;

CREATE OR REPLACE FUNCTION a1_bind_verified_identity_credential(
  p_organization_id UUID,
  p_project_id UUID,
  p_receipt_digest TEXT,
  p_principal_id UUID,
  p_idempotency_digest TEXT,
  p_request_digest TEXT,
  p_event_digest TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_now TIMESTAMPTZ := clock_timestamp();
  receipt identity_verification_receipts%ROWTYPE;
  principal identity_principals%ROWTYPE;
  existing_credential identity_credentials%ROWTYPE;
  created_credential_id UUID;
BEGIN
  PERFORM a1_identity_verification_assert_scope(
    p_organization_id, p_project_id
  );
  IF NOT a1_identity_digest_valid(p_receipt_digest)
     OR NOT a1_identity_digest_valid(p_idempotency_digest)
     OR NOT a1_identity_digest_valid(p_request_digest)
     OR NOT a1_identity_digest_valid(p_event_digest)
     OR NOT a1_identity_public_metadata(p_metadata) THEN
    RAISE EXCEPTION 'identity verification mutation is invalid'
      USING ERRCODE = '22023';
  END IF;

  SELECT *
    INTO receipt
    FROM identity_verification_receipts
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND receipt_digest = p_receipt_digest
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity verification proof is invalid'
      USING ERRCODE = '42501';
  END IF;
  IF receipt.status = 'consumed' THEN
    IF receipt.idempotency_digest = p_idempotency_digest
       AND receipt.request_digest = p_request_digest
       AND receipt.mutation_kind = 'bind' THEN
      RETURN receipt.mutation_result_id;
    END IF;
    RAISE EXCEPTION 'idempotency_conflict'
      USING ERRCODE = '23505';
  END IF;
  IF receipt.status <> 'verified'
     OR receipt.purpose <> 'credential_binding'
     OR receipt.principal_id IS DISTINCT FROM p_principal_id THEN
    RAISE EXCEPTION 'identity verification proof is invalid'
      USING ERRCODE = '42501';
  END IF;

  SELECT *
    INTO principal
    FROM identity_principals
   WHERE id = p_principal_id
     AND status = 'active'
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity verification principal is unavailable'
      USING ERRCODE = '42501';
  END IF;

  SELECT *
    INTO existing_credential
    FROM identity_credentials
   WHERE provider = receipt.channel
     AND provider_environment = 'production'
     AND subject_digest = receipt.subject_digest
   FOR UPDATE;
  IF FOUND THEN
    RAISE EXCEPTION 'credential_link_conflict'
      USING ERRCODE = '23505';
  END IF;

  IF EXISTS (
    SELECT 1
      FROM identity_verification_receipts
     WHERE organization_id = p_organization_id
       AND project_id = p_project_id
       AND idempotency_digest = p_idempotency_digest
       AND request_digest <> p_request_digest
  ) THEN
    RAISE EXCEPTION 'idempotency_conflict'
      USING ERRCODE = '23505';
  END IF;

  INSERT INTO identity_credentials (
    principal_id, provider, provider_environment, credential_kind,
    subject_digest, status, login_enabled, verified_at, metadata
  ) VALUES (
    p_principal_id, receipt.channel, 'production',
    CASE WHEN receipt.channel = 'phone' THEN 'phone_otp' ELSE 'email_otp' END,
    receipt.subject_digest, 'active', TRUE, v_now, p_metadata
  )
  RETURNING id INTO created_credential_id;

  UPDATE identity_verification_receipts
     SET status = 'consumed',
         consumed_at = v_now,
         idempotency_digest = p_idempotency_digest,
         request_digest = p_request_digest,
         mutation_kind = 'bind',
         mutation_result_id = created_credential_id
   WHERE id = receipt.id
     AND status = 'verified'
     AND consumed_at IS NULL;

  INSERT INTO identity_verification_audit_events (
    organization_id, project_id, challenge_id, principal_id,
    event_type, outcome_code, attempt_number,
    request_context_digest, event_digest, metadata
  ) VALUES (
    receipt.organization_id, receipt.project_id, receipt.challenge_id,
    p_principal_id, 'credential_bound', 'bound', 0,
    receipt.request_context_digest, p_event_digest, p_metadata
  );
  RETURN created_credential_id;
END;
$$;

CREATE OR REPLACE FUNCTION a1_login_with_verified_identity(
  p_organization_id UUID,
  p_project_id UUID,
  p_receipt_digest TEXT,
  p_session_digest TEXT,
  p_rotation_family_digest TEXT,
  p_expires_at TIMESTAMPTZ,
  p_idempotency_digest TEXT,
  p_request_digest TEXT,
  p_event_digest TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_now TIMESTAMPTZ := clock_timestamp();
  receipt identity_verification_receipts%ROWTYPE;
  principal identity_principals%ROWTYPE;
  credential identity_credentials%ROWTYPE;
  created_session_id UUID;
BEGIN
  PERFORM a1_identity_verification_assert_scope(
    p_organization_id, p_project_id
  );
  IF NOT a1_identity_digest_valid(p_receipt_digest)
     OR NOT a1_identity_digest_valid(p_session_digest)
     OR NOT a1_identity_digest_valid(p_rotation_family_digest)
     OR NOT a1_identity_digest_valid(p_idempotency_digest)
     OR NOT a1_identity_digest_valid(p_request_digest)
     OR NOT a1_identity_digest_valid(p_event_digest)
     OR p_expires_at <= v_now
     OR NOT a1_identity_public_metadata(p_metadata) THEN
    RAISE EXCEPTION 'identity verification mutation is invalid'
      USING ERRCODE = '22023';
  END IF;

  SELECT *
    INTO receipt
    FROM identity_verification_receipts
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND receipt_digest = p_receipt_digest
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity verification proof is invalid'
      USING ERRCODE = '42501';
  END IF;
  IF receipt.status = 'consumed' THEN
    IF receipt.idempotency_digest = p_idempotency_digest
       AND receipt.request_digest = p_request_digest
       AND receipt.mutation_kind = 'login' THEN
      RETURN receipt.mutation_result_id;
    END IF;
    RAISE EXCEPTION 'idempotency_conflict'
      USING ERRCODE = '23505';
  END IF;
  IF receipt.status <> 'verified'
     OR receipt.purpose <> 'login' THEN
    RAISE EXCEPTION 'identity verification proof is invalid'
      USING ERRCODE = '42501';
  END IF;

  SELECT *
    INTO credential
    FROM identity_credentials
   WHERE provider = receipt.channel
     AND provider_environment = 'production'
     AND subject_digest = receipt.subject_digest
     AND status = 'active'
     AND login_enabled
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity verification credential is unavailable'
      USING ERRCODE = '42501';
  END IF;

  SELECT *
    INTO principal
    FROM identity_principals
   WHERE id = credential.principal_id
     AND status = 'active'
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity verification principal is unavailable'
      USING ERRCODE = '42501';
  END IF;

  INSERT INTO identity_sessions (
    principal_id, credential_id, organization_id, project_id,
    session_digest, rotation_family_digest, status, assurance_level,
    authenticated_at, expires_at, metadata
  ) VALUES (
    principal.id, credential.id, p_organization_id, p_project_id,
    p_session_digest, p_rotation_family_digest, 'active', 'aal1',
    v_now, p_expires_at, p_metadata
  )
  RETURNING id INTO created_session_id;

  UPDATE identity_credentials
     SET last_authenticated_at = v_now,
         updated_at = v_now
   WHERE id = credential.id;

  UPDATE identity_verification_receipts
     SET status = 'consumed',
         consumed_at = v_now,
         idempotency_digest = p_idempotency_digest,
         request_digest = p_request_digest,
         mutation_kind = 'login',
         mutation_result_id = created_session_id
   WHERE id = receipt.id
     AND status = 'verified'
     AND consumed_at IS NULL;

  INSERT INTO identity_verification_audit_events (
    organization_id, project_id, challenge_id, principal_id,
    event_type, outcome_code, attempt_number,
    request_context_digest, event_digest, metadata
  ) VALUES (
    receipt.organization_id, receipt.project_id, receipt.challenge_id,
    principal.id, 'login_succeeded', 'authenticated', 0,
    receipt.request_context_digest, p_event_digest, p_metadata
  );
  RETURN created_session_id;
END;
$$;

CREATE OR REPLACE FUNCTION a1_recover_verified_identity(
  p_organization_id UUID,
  p_project_id UUID,
  p_receipt_digest TEXT,
  p_session_digest TEXT,
  p_rotation_family_digest TEXT,
  p_expires_at TIMESTAMPTZ,
  p_idempotency_digest TEXT,
  p_request_digest TEXT,
  p_event_digest TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_now TIMESTAMPTZ := clock_timestamp();
  receipt identity_verification_receipts%ROWTYPE;
  principal identity_principals%ROWTYPE;
  credential identity_credentials%ROWTYPE;
  prior_session identity_sessions%ROWTYPE;
  created_session_id UUID;
BEGIN
  PERFORM a1_identity_verification_assert_scope(
    p_organization_id, p_project_id
  );
  IF NOT a1_identity_digest_valid(p_receipt_digest)
     OR NOT a1_identity_digest_valid(p_session_digest)
     OR NOT a1_identity_digest_valid(p_rotation_family_digest)
     OR NOT a1_identity_digest_valid(p_idempotency_digest)
     OR NOT a1_identity_digest_valid(p_request_digest)
     OR NOT a1_identity_digest_valid(p_event_digest)
     OR p_expires_at <= v_now
     OR NOT a1_identity_public_metadata(p_metadata) THEN
    RAISE EXCEPTION 'identity verification mutation is invalid'
      USING ERRCODE = '22023';
  END IF;

  SELECT *
    INTO receipt
    FROM identity_verification_receipts
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND receipt_digest = p_receipt_digest
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity verification proof is invalid'
      USING ERRCODE = '42501';
  END IF;
  IF receipt.status = 'consumed' THEN
    IF receipt.idempotency_digest = p_idempotency_digest
       AND receipt.request_digest = p_request_digest
       AND receipt.mutation_kind = 'recovery' THEN
      RETURN receipt.mutation_result_id;
    END IF;
    RAISE EXCEPTION 'idempotency_conflict'
      USING ERRCODE = '23505';
  END IF;
  IF receipt.status <> 'verified'
     OR receipt.purpose <> 'account_recovery'
     OR receipt.principal_id IS NULL THEN
    RAISE EXCEPTION 'identity verification proof is invalid'
      USING ERRCODE = '42501';
  END IF;

  SELECT *
    INTO principal
    FROM identity_principals
   WHERE id = receipt.principal_id
     AND status = 'active'
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity verification principal is unavailable'
      USING ERRCODE = '42501';
  END IF;

  SELECT *
    INTO credential
    FROM identity_credentials
   WHERE principal_id = principal.id
     AND provider = receipt.channel
     AND provider_environment = 'production'
     AND subject_digest = receipt.subject_digest
     AND status = 'active'
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity verification credential is unavailable'
      USING ERRCODE = '42501';
  END IF;

  SELECT *
    INTO prior_session
    FROM identity_sessions
   WHERE principal_id = principal.id
     AND organization_id = p_organization_id
     AND project_id = p_project_id
     AND status = 'active'
   ORDER BY authenticated_at DESC
   LIMIT 1
   FOR UPDATE;

  UPDATE identity_sessions
     SET status = 'revoked',
         revoked_at = v_now,
         revoke_reason_code = 'account_recovery'
   WHERE principal_id = principal.id
     AND organization_id = p_organization_id
     AND project_id = p_project_id
     AND status = 'active';

  INSERT INTO identity_sessions (
    principal_id, credential_id, organization_id, project_id,
    session_digest, rotation_family_digest, status, assurance_level,
    authenticated_at, expires_at, metadata
  ) VALUES (
    principal.id, credential.id, p_organization_id, p_project_id,
    p_session_digest, p_rotation_family_digest, 'active', 'aal2',
    v_now, p_expires_at, p_metadata
  )
  RETURNING id INTO created_session_id;

  UPDATE identity_verification_receipts
     SET status = 'consumed',
         consumed_at = v_now,
         idempotency_digest = p_idempotency_digest,
         request_digest = p_request_digest,
         mutation_kind = 'recovery',
         mutation_result_id = created_session_id
   WHERE id = receipt.id
     AND status = 'verified'
     AND consumed_at IS NULL;

  INSERT INTO identity_verification_audit_events (
    organization_id, project_id, challenge_id, principal_id,
    event_type, outcome_code, attempt_number,
    request_context_digest, event_digest, metadata
  ) VALUES (
    receipt.organization_id, receipt.project_id, receipt.challenge_id,
    principal.id, 'recovery_succeeded', 'recovered', 0,
    receipt.request_context_digest, p_event_digest, p_metadata
  );
  RETURN created_session_id;
END;
$$;

CREATE OR REPLACE FUNCTION a1_identity_verification_receipt_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'identity verification receipts cannot be deleted'
      USING ERRCODE = '55000';
  END IF;
  IF OLD.status <> 'verified'
     OR NEW.status <> 'consumed'
     OR OLD.consumed_at IS NOT NULL
     OR NEW.consumed_at IS NULL
     OR OLD.id <> NEW.id
     OR OLD.organization_id <> NEW.organization_id
     OR OLD.project_id <> NEW.project_id
     OR OLD.challenge_id <> NEW.challenge_id
     OR OLD.principal_id IS DISTINCT FROM NEW.principal_id
     OR OLD.channel <> NEW.channel
     OR OLD.purpose <> NEW.purpose
     OR OLD.subject_digest <> NEW.subject_digest
     OR OLD.request_context_digest <> NEW.request_context_digest
     OR OLD.receipt_digest <> NEW.receipt_digest
     OR OLD.verified_at <> NEW.verified_at
     OR OLD.created_at <> NEW.created_at THEN
    RAISE EXCEPTION 'identity verification receipt transition rejected'
      USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS identity_verification_receipts_append_only
  ON identity_verification_receipts;
CREATE TRIGGER identity_verification_receipts_append_only
BEFORE UPDATE OR DELETE ON identity_verification_receipts
FOR EACH ROW EXECUTE FUNCTION a1_identity_verification_receipt_transition();

DROP TRIGGER IF EXISTS identity_verification_audit_append_only
  ON identity_verification_audit_events;
CREATE TRIGGER identity_verification_audit_append_only
BEFORE UPDATE OR DELETE ON identity_verification_audit_events
FOR EACH ROW EXECUTE FUNCTION a1_identity_reject_append_only_mutation();

DROP TRIGGER IF EXISTS identity_verification_challenges_no_hard_delete
  ON identity_verification_challenges;
CREATE TRIGGER identity_verification_challenges_no_hard_delete
BEFORE DELETE ON identity_verification_challenges
FOR EACH ROW EXECUTE FUNCTION a1_identity_reject_hard_delete();

DROP TRIGGER IF EXISTS identity_verification_cooldowns_no_hard_delete
  ON identity_verification_cooldowns;
CREATE TRIGGER identity_verification_cooldowns_no_hard_delete
BEFORE DELETE ON identity_verification_cooldowns
FOR EACH ROW EXECUTE FUNCTION a1_identity_reject_hard_delete();

DROP TRIGGER IF EXISTS identity_verification_delivery_no_hard_delete
  ON identity_verification_delivery_outbox;
CREATE TRIGGER identity_verification_delivery_no_hard_delete
BEFORE DELETE ON identity_verification_delivery_outbox
FOR EACH ROW EXECUTE FUNCTION a1_identity_reject_hard_delete();

DROP TRIGGER IF EXISTS identity_verification_abuse_no_hard_delete
  ON identity_verification_abuse_budgets;
CREATE TRIGGER identity_verification_abuse_no_hard_delete
BEFORE DELETE ON identity_verification_abuse_budgets
FOR EACH ROW EXECUTE FUNCTION a1_identity_reject_hard_delete();

ALTER TABLE identity_verification_cooldowns ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_verification_challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_verification_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_verification_audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_verification_delivery_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_verification_abuse_budgets ENABLE ROW LEVEL SECURITY;

ALTER TABLE identity_verification_cooldowns FORCE ROW LEVEL SECURITY;
ALTER TABLE identity_verification_challenges FORCE ROW LEVEL SECURITY;
ALTER TABLE identity_verification_receipts FORCE ROW LEVEL SECURITY;
ALTER TABLE identity_verification_audit_events FORCE ROW LEVEL SECURITY;
ALTER TABLE identity_verification_delivery_outbox FORCE ROW LEVEL SECURITY;
ALTER TABLE identity_verification_abuse_budgets FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS identity_verification_cooldowns_scope_access
  ON identity_verification_cooldowns;
DROP POLICY IF EXISTS identity_verification_challenges_scope_access
  ON identity_verification_challenges;
DROP POLICY IF EXISTS identity_verification_receipts_scope_access
  ON identity_verification_receipts;
DROP POLICY IF EXISTS identity_verification_audit_scope_access
  ON identity_verification_audit_events;
DROP POLICY IF EXISTS identity_verification_delivery_scope_access
  ON identity_verification_delivery_outbox;
DROP POLICY IF EXISTS identity_verification_abuse_scope_access
  ON identity_verification_abuse_budgets;

CREATE POLICY identity_verification_cooldowns_scope_access
  ON identity_verification_cooldowns
  USING (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
  )
  WITH CHECK (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
  );

CREATE POLICY identity_verification_challenges_scope_access
  ON identity_verification_challenges
  USING (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
    AND (
      principal_id IS NULL
      OR principal_id = a1_current_principal_id()
    )
  )
  WITH CHECK (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
    AND (
      principal_id IS NULL
      OR principal_id = a1_current_principal_id()
    )
  );

CREATE POLICY identity_verification_receipts_scope_access
  ON identity_verification_receipts
  USING (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
    AND (
      principal_id IS NULL
      OR principal_id = a1_current_principal_id()
    )
  )
  WITH CHECK (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
    AND (
      principal_id IS NULL
      OR principal_id = a1_current_principal_id()
    )
  );

CREATE POLICY identity_verification_audit_scope_access
  ON identity_verification_audit_events
  USING (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
    AND (
      principal_id IS NULL
      OR principal_id = a1_current_principal_id()
    )
  )
  WITH CHECK (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
    AND (
      principal_id IS NULL
      OR principal_id = a1_current_principal_id()
    )
  );

CREATE POLICY identity_verification_delivery_scope_access
  ON identity_verification_delivery_outbox
  USING (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
  )
  WITH CHECK (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
  );

CREATE POLICY identity_verification_abuse_scope_access
  ON identity_verification_abuse_budgets
  USING (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
  )
  WITH CHECK (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
  );

REVOKE ALL ON TABLE identity_verification_cooldowns FROM PUBLIC;
REVOKE ALL ON TABLE identity_verification_challenges FROM PUBLIC;
REVOKE ALL ON TABLE identity_verification_receipts FROM PUBLIC;
REVOKE ALL ON TABLE identity_verification_audit_events FROM PUBLIC;
REVOKE ALL ON TABLE identity_verification_delivery_outbox FROM PUBLIC;
REVOKE ALL ON TABLE identity_verification_abuse_budgets FROM PUBLIC;

REVOKE ALL ON FUNCTION a1_identity_verification_assert_scope(UUID, UUID)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_issue_identity_verification_challenge(
  UUID, UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TIMESTAMPTZ, INTEGER, INTEGER, TEXT, JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_verify_consume_identity_challenge(
  UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_verify_identity_verification_attempt(
  UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_bind_verified_identity_credential(
  UUID, UUID, TEXT, UUID, TEXT, TEXT, TEXT, JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_login_with_verified_identity(
  UUID, UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, TEXT, TEXT, JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_recover_verified_identity(
  UUID, UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, TEXT, TEXT, JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_identity_verification_receipt_transition()
  FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a1_runtime') THEN
    REVOKE ALL ON TABLE identity_verification_cooldowns FROM a1_runtime;
    REVOKE ALL ON TABLE identity_verification_challenges FROM a1_runtime;
    REVOKE ALL ON TABLE identity_verification_receipts FROM a1_runtime;
    REVOKE ALL ON TABLE identity_verification_audit_events FROM a1_runtime;
    REVOKE ALL ON TABLE identity_verification_delivery_outbox FROM a1_runtime;
    REVOKE ALL ON TABLE identity_verification_abuse_budgets FROM a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_issue_identity_verification_challenge(
      UUID, UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
      TIMESTAMPTZ, INTEGER, INTEGER, TEXT, JSONB
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_verify_consume_identity_challenge(
      UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_verify_identity_verification_attempt(
      UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, JSONB
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_bind_verified_identity_credential(
      UUID, UUID, TEXT, UUID, TEXT, TEXT, TEXT, JSONB
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_login_with_verified_identity(
      UUID, UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ,
      TEXT, TEXT, TEXT, JSONB
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_recover_verified_identity(
      UUID, UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ,
      TEXT, TEXT, TEXT, JSONB
    ) TO a1_runtime;
  END IF;
END;
$$;

COMMIT;
