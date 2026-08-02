-- Atomic email registration and canonical session handoff.
-- Registration is deliberately distinct from credential binding: it is
-- accountless, email-only, and creates exactly one new canonical principal.
-- Raw email addresses, OTPs, and bearer tokens never cross this boundary.

BEGIN;

ALTER TABLE identity_verification_cooldowns
  DROP CONSTRAINT IF EXISTS identity_verification_cooldowns_purpose_check;
ALTER TABLE identity_verification_cooldowns
  ADD CONSTRAINT identity_verification_cooldowns_purpose_check CHECK (
    purpose IN (
      'registration', 'login', 'credential_binding',
      'account_recovery', 'step_up'
    )
  );

ALTER TABLE identity_verification_challenges
  DROP CONSTRAINT IF EXISTS identity_verification_challenges_purpose_check;
ALTER TABLE identity_verification_challenges
  ADD CONSTRAINT identity_verification_challenges_purpose_check CHECK (
    purpose IN (
      'registration', 'login', 'credential_binding',
      'account_recovery', 'step_up'
    )
  );
ALTER TABLE identity_verification_challenges
  DROP CONSTRAINT IF EXISTS identity_verification_challenges_principal_purpose_check;
ALTER TABLE identity_verification_challenges
  ADD CONSTRAINT identity_verification_challenges_principal_purpose_check CHECK (
    (purpose IN ('registration', 'login') OR principal_id IS NOT NULL)
    AND (purpose <> 'registration' OR principal_id IS NULL)
  );

ALTER TABLE identity_verification_receipts
  DROP CONSTRAINT IF EXISTS identity_verification_receipts_purpose_check;
ALTER TABLE identity_verification_receipts
  ADD CONSTRAINT identity_verification_receipts_purpose_check CHECK (
    purpose IN (
      'registration', 'login', 'credential_binding',
      'account_recovery', 'step_up'
    )
  );
ALTER TABLE identity_verification_receipts
  DROP CONSTRAINT IF EXISTS identity_verification_receipts_mutation_kind_check;
ALTER TABLE identity_verification_receipts
  ADD CONSTRAINT identity_verification_receipts_mutation_kind_check CHECK (
    mutation_kind IS NULL
    OR mutation_kind IN ('registration', 'bind', 'login', 'recovery')
  );

ALTER TABLE identity_verification_delivery_outbox
  DROP CONSTRAINT IF EXISTS identity_verification_delivery_outbox_purpose_check;
ALTER TABLE identity_verification_delivery_outbox
  ADD CONSTRAINT identity_verification_delivery_outbox_purpose_check CHECK (
    purpose IN (
      'registration', 'login', 'credential_binding',
      'account_recovery', 'step_up'
    )
  );

ALTER TABLE identity_verification_abuse_budgets
  DROP CONSTRAINT IF EXISTS identity_verification_abuse_budgets_purpose_check;
ALTER TABLE identity_verification_abuse_budgets
  ADD CONSTRAINT identity_verification_abuse_budgets_purpose_check CHECK (
    purpose IN (
      'registration', 'login', 'credential_binding',
      'account_recovery', 'step_up'
    )
  );

ALTER TABLE identity_verification_audit_events
  DROP CONSTRAINT IF EXISTS identity_verification_audit_events_event_type_check;
ALTER TABLE identity_verification_audit_events
  ADD CONSTRAINT identity_verification_audit_events_event_type_check CHECK (
    event_type IN (
      'challenge_issued',
      'challenge_rejected',
      'challenge_locked',
      'challenge_expired',
      'challenge_consumed',
      'proof_verified',
      'credential_bound',
      'registration_succeeded',
      'login_succeeded',
      'recovery_succeeded',
      'delivery_failed'
    )
  );
ALTER TABLE identity_verification_audit_events
  DROP CONSTRAINT IF EXISTS identity_verification_audit_events_outcome_code_check;
ALTER TABLE identity_verification_audit_events
  ADD CONSTRAINT identity_verification_audit_events_outcome_code_check CHECK (
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
      'registered',
      'authenticated',
      'recovered',
      'idempotency_conflict',
      'delivery_failed'
    )
  );

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
SET search_path = pg_catalog, public, pg_temp
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
       'registration', 'login', 'credential_binding',
       'account_recovery', 'step_up'
     )
     OR (
       p_purpose = 'registration'
       AND (p_channel <> 'email' OR p_principal_id IS NOT NULL)
     )
     OR (
       p_purpose NOT IN ('registration', 'login')
       AND p_principal_id IS NULL
     )
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

CREATE OR REPLACE FUNCTION a1_register_with_verified_identity_with_refresh(
  p_organization_id UUID,
  p_project_id UUID,
  p_receipt_digest TEXT,
  p_session_digest TEXT,
  p_refresh_digest TEXT,
  p_rotation_family_digest TEXT,
  p_access_expires_at TIMESTAMPTZ,
  p_refresh_expires_at TIMESTAMPTZ,
  p_idempotency_digest TEXT,
  p_request_digest TEXT,
  p_event_digest TEXT,
  p_display_label TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE (
  session_id UUID,
  principal_id UUID,
  credential_id UUID
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  v_now TIMESTAMPTZ := clock_timestamp();
  receipt identity_verification_receipts%ROWTYPE;
  issued_session identity_sessions%ROWTYPE;
  v_principal_id UUID;
  v_credential_id UUID;
  v_session_id UUID;
  v_organization_membership_id UUID;
  changed_count INTEGER;
BEGIN
  PERFORM a1_identity_verification_assert_scope(
    p_organization_id, p_project_id
  );

  IF NOT a1_identity_digest_valid(p_receipt_digest)
     OR NOT a1_identity_digest_valid(p_session_digest)
     OR NOT a1_identity_digest_valid(p_refresh_digest)
     OR NOT a1_identity_digest_valid(p_rotation_family_digest)
     OR NOT a1_identity_digest_valid(p_idempotency_digest)
     OR NOT a1_identity_digest_valid(p_request_digest)
     OR NOT a1_identity_digest_valid(p_event_digest)
     OR p_session_digest = p_refresh_digest
     OR p_access_expires_at <= v_now
     OR p_refresh_expires_at <= p_access_expires_at
     OR length(COALESCE(p_display_label, '')) > 256
     OR COALESCE(p_display_label, '') <> btrim(COALESCE(p_display_label, ''))
     OR COALESCE(p_display_label, '') ~ '[\r\n]'
     OR NOT a1_identity_public_metadata(p_metadata) THEN
    RAISE EXCEPTION 'identity verified registration is invalid'
      USING ERRCODE = '22023';
  END IF;

  SELECT receipt_row.*
    INTO receipt
    FROM identity_verification_receipts AS receipt_row
   WHERE receipt_row.organization_id = p_organization_id
     AND receipt_row.project_id = p_project_id
     AND receipt_row.receipt_digest = p_receipt_digest
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity verification proof is invalid'
      USING ERRCODE = '42501';
  END IF;

  IF receipt.status = 'consumed' THEN
    IF receipt.idempotency_digest <> p_idempotency_digest
       OR receipt.request_digest <> p_request_digest
       OR receipt.mutation_kind <> 'registration' THEN
      RAISE EXCEPTION 'idempotency_conflict'
        USING ERRCODE = '23505';
    END IF;

    SELECT session_row.*
      INTO issued_session
      FROM identity_sessions AS session_row
     WHERE session_row.id = receipt.mutation_result_id
       AND session_row.organization_id = p_organization_id
       AND session_row.project_id = p_project_id
       AND session_row.credential_id IS NOT NULL;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'identity verified registration session is unavailable'
        USING ERRCODE = '42501';
    END IF;

    RETURN QUERY SELECT
      issued_session.id,
      issued_session.principal_id,
      issued_session.credential_id;
    RETURN;
  END IF;

  IF receipt.status <> 'verified'
     OR receipt.purpose <> 'registration'
     OR receipt.channel <> 'email'
     OR receipt.principal_id IS NOT NULL THEN
    RAISE EXCEPTION 'identity verification proof is invalid'
      USING ERRCODE = '42501';
  END IF;

  SELECT registered_principal_id, registered_credential_id
    INTO v_principal_id, v_credential_id
    FROM a1_register_identity_lifecycle_credential(
      'email',
      'email_otp',
      ARRAY[receipt.subject_digest],
      p_display_label,
      receipt.subject_digest,
      'email',
      p_request_digest,
      v_now
    );
  IF v_principal_id IS NULL OR v_credential_id IS NULL THEN
    RAISE EXCEPTION 'identity verified registration failed'
      USING ERRCODE = '40001';
  END IF;

  INSERT INTO identity_organization_memberships (
    organization_id,
    principal_id,
    role,
    status,
    activated_at,
    metadata
  ) VALUES (
    p_organization_id,
    v_principal_id,
    'member',
    'active',
    v_now,
    '{}'::JSONB
  )
  RETURNING id INTO v_organization_membership_id;

  INSERT INTO identity_project_memberships (
    organization_id,
    project_id,
    principal_id,
    organization_membership_id,
    role,
    status,
    activated_at,
    metadata
  ) VALUES (
    p_organization_id,
    p_project_id,
    v_principal_id,
    v_organization_membership_id,
    'member',
    'active',
    v_now,
    '{}'::JSONB
  );

  PERFORM set_config('app.a1_principal_id', v_principal_id::TEXT, TRUE);

  SELECT issued.session_id
    INTO v_session_id
    FROM a1_issue_identity_session_with_refresh(
      p_organization_id,
      p_project_id,
      v_principal_id,
      v_credential_id,
      p_session_digest,
      p_refresh_digest,
      p_rotation_family_digest,
      p_access_expires_at,
      p_refresh_expires_at,
      'aal1',
      p_idempotency_digest,
      p_request_digest,
      p_metadata
    ) AS issued;
  IF v_session_id IS NULL THEN
    RAISE EXCEPTION 'identity verified registration session is unavailable'
      USING ERRCODE = '40001';
  END IF;

  UPDATE identity_verification_receipts AS receipt_row
     SET status = 'consumed',
         consumed_at = v_now,
         idempotency_digest = p_idempotency_digest,
         request_digest = p_request_digest,
         mutation_kind = 'registration',
         mutation_result_id = v_session_id
   WHERE receipt_row.id = receipt.id
     AND receipt_row.status = 'verified'
     AND receipt_row.consumed_at IS NULL;
  GET DIAGNOSTICS changed_count = ROW_COUNT;
  IF changed_count <> 1 THEN
    RAISE EXCEPTION 'identity verified registration conflict'
      USING ERRCODE = '40001';
  END IF;

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
    receipt.organization_id,
    receipt.project_id,
    receipt.challenge_id,
    v_principal_id,
    'registration_succeeded',
    'registered',
    0,
    receipt.request_context_digest,
    p_event_digest,
    p_metadata
  );

  RETURN QUERY SELECT v_session_id, v_principal_id, v_credential_id;
END;
$$;

CREATE OR REPLACE FUNCTION a1_login_with_verified_identity_with_refresh_result(
  p_organization_id UUID,
  p_project_id UUID,
  p_receipt_digest TEXT,
  p_session_digest TEXT,
  p_refresh_digest TEXT,
  p_rotation_family_digest TEXT,
  p_access_expires_at TIMESTAMPTZ,
  p_refresh_expires_at TIMESTAMPTZ,
  p_idempotency_digest TEXT,
  p_request_digest TEXT,
  p_event_digest TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE (
  session_id UUID,
  principal_id UUID,
  credential_id UUID
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  v_session_id UUID;
  issued_session identity_sessions%ROWTYPE;
BEGIN
  v_session_id := a1_login_with_verified_identity_with_refresh(
    p_organization_id,
    p_project_id,
    p_receipt_digest,
    p_session_digest,
    p_refresh_digest,
    p_rotation_family_digest,
    p_access_expires_at,
    p_refresh_expires_at,
    p_idempotency_digest,
    p_request_digest,
    p_event_digest,
    p_metadata
  );

  SELECT session_row.*
    INTO issued_session
    FROM identity_sessions AS session_row
   WHERE session_row.id = v_session_id
     AND session_row.organization_id = p_organization_id
     AND session_row.project_id = p_project_id
     AND session_row.credential_id IS NOT NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity verified login session is unavailable'
      USING ERRCODE = '42501';
  END IF;

  RETURN QUERY SELECT
    issued_session.id,
    issued_session.principal_id,
    issued_session.credential_id;
END;
$$;

CREATE OR REPLACE FUNCTION a1_recover_verified_identity_with_refresh_result(
  p_organization_id UUID,
  p_project_id UUID,
  p_receipt_digest TEXT,
  p_session_digest TEXT,
  p_refresh_digest TEXT,
  p_rotation_family_digest TEXT,
  p_access_expires_at TIMESTAMPTZ,
  p_refresh_expires_at TIMESTAMPTZ,
  p_idempotency_digest TEXT,
  p_request_digest TEXT,
  p_event_digest TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE (
  session_id UUID,
  principal_id UUID,
  credential_id UUID
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  v_session_id UUID;
  issued_session identity_sessions%ROWTYPE;
BEGIN
  v_session_id := a1_recover_verified_identity_with_refresh(
    p_organization_id,
    p_project_id,
    p_receipt_digest,
    p_session_digest,
    p_refresh_digest,
    p_rotation_family_digest,
    p_access_expires_at,
    p_refresh_expires_at,
    p_idempotency_digest,
    p_request_digest,
    p_event_digest,
    p_metadata
  );

  SELECT session_row.*
    INTO issued_session
    FROM identity_sessions AS session_row
   WHERE session_row.id = v_session_id
     AND session_row.organization_id = p_organization_id
     AND session_row.project_id = p_project_id
     AND session_row.credential_id IS NOT NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity verified recovery session is unavailable'
      USING ERRCODE = '42501';
  END IF;

  RETURN QUERY SELECT
    issued_session.id,
    issued_session.principal_id,
    issued_session.credential_id;
END;
$$;

REVOKE ALL ON FUNCTION a1_register_with_verified_identity_with_refresh(
  UUID,UUID,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,
  TEXT,TEXT,TEXT,TEXT,JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_login_with_verified_identity_with_refresh_result(
  UUID,UUID,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,
  TEXT,TEXT,TEXT,JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_recover_verified_identity_with_refresh_result(
  UUID,UUID,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,
  TEXT,TEXT,TEXT,JSONB
) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a1_runtime') THEN
    REVOKE ALL ON FUNCTION a1_login_with_verified_identity_with_refresh(
      UUID,UUID,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,
      TEXT,TEXT,TEXT,JSONB
    ) FROM a1_runtime;
    REVOKE ALL ON FUNCTION a1_recover_verified_identity_with_refresh(
      UUID,UUID,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,
      TEXT,TEXT,TEXT,JSONB
    ) FROM a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_register_with_verified_identity_with_refresh(
      UUID,UUID,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,
      TEXT,TEXT,TEXT,TEXT,JSONB
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_login_with_verified_identity_with_refresh_result(
      UUID,UUID,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,
      TEXT,TEXT,TEXT,JSONB
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_recover_verified_identity_with_refresh_result(
      UUID,UUID,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,
      TEXT,TEXT,TEXT,JSONB
    ) TO a1_runtime;
  END IF;
END
$$;

COMMIT;
