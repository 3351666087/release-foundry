-- Complete the durable TOTP recovery lifecycle. PostgreSQL is the sole
-- mutation authority for canonical account state, sessions, exact replay and
-- audit/outbox writes. Raw TOTP secrets, recovery codes and processor tokens
-- remain outside PostgreSQL.
BEGIN;

ALTER TABLE identity_account_security
  DROP CONSTRAINT IF EXISTS identity_totp_posture_check;
ALTER TABLE identity_account_security
  DROP CONSTRAINT IF EXISTS identity_recovery_code_count_check;

UPDATE identity_account_security
   SET totp_pending_at = NULL
 WHERE two_factor_status = 'enabled'
   AND totp_pending_at IS NOT NULL;

ALTER TABLE identity_account_security
  ADD CONSTRAINT identity_totp_posture_check CHECK (
    (
      two_factor_status = 'disabled'
      AND totp_secret_ref IS NULL
      AND totp_secret_digest IS NULL
      AND totp_pending_at IS NULL
      AND two_factor_enrolled_at IS NULL
      AND recovery_code_batch_digest IS NULL
      AND recovery_codes_remaining = 0
    )
    OR
    (
      two_factor_status = 'pending'
      AND totp_secret_ref IS NOT NULL
      AND length(totp_secret_ref) >= 16
      AND a1_identity_digest_valid(totp_secret_digest)
      AND totp_pending_at IS NOT NULL
      AND two_factor_enrolled_at IS NULL
      AND recovery_code_batch_digest IS NULL
      AND recovery_codes_remaining = 0
    )
    OR
    (
      two_factor_status = 'enabled'
      AND totp_secret_ref IS NOT NULL
      AND length(totp_secret_ref) >= 16
      AND a1_identity_digest_valid(totp_secret_digest)
      AND totp_pending_at IS NULL
      AND two_factor_enrolled_at IS NOT NULL
      AND a1_identity_digest_valid(recovery_code_batch_digest)
      AND recovery_codes_remaining BETWEEN 0 AND 20
    )
  );
ALTER TABLE identity_account_security
  ADD CONSTRAINT identity_recovery_code_count_check
  CHECK (recovery_codes_remaining BETWEEN 0 AND 20);

ALTER TABLE identity_security_receipts
  DROP CONSTRAINT IF EXISTS identity_security_receipts_purpose_check;
ALTER TABLE identity_security_receipts
  ADD CONSTRAINT identity_security_receipts_purpose_check CHECK (
    purpose IN (
      'password_enroll','password_change','password_recovery',
      'mfa_enroll','mfa_confirm','mfa_disable','mfa_recovery',
      'mfa_recovery_consume','mfa_recovery_rotate','credential_bind'
    )
  );

ALTER TABLE identity_security_mutation_tickets
  ADD COLUMN IF NOT EXISTS expected_recovery_batch_digest TEXT,
  ADD COLUMN IF NOT EXISTS expected_recovery_code_count INTEGER;
ALTER TABLE identity_security_mutation_tickets
  DROP CONSTRAINT IF EXISTS identity_security_mutation_tickets_operation_check;
ALTER TABLE identity_security_mutation_tickets
  DROP CONSTRAINT IF EXISTS identity_security_mutation_ticket_payload_check;
ALTER TABLE identity_security_mutation_tickets
  ADD CONSTRAINT identity_security_mutation_tickets_operation_check CHECK (
    operation IN (
      'password_enroll','password_change','password_recovery',
      'mfa_enroll','mfa_confirm','mfa_recovery_consume',
      'mfa_recovery_rotate','mfa_disable','credential_bind'
    )
  );
ALTER TABLE identity_security_mutation_tickets
  ADD CONSTRAINT identity_security_mutation_ticket_payload_check CHECK (
    (
      operation IN (
        'password_enroll','password_change','password_recovery','mfa_enroll'
      )
      AND secret_ref IS NOT NULL
      AND length(secret_ref) >= 16
      AND a1_identity_digest_valid(secret_digest)
      AND expected_recovery_batch_digest IS NULL
      AND expected_recovery_code_count IS NULL
      AND recovery_batch_digest IS NULL
      AND recovery_code_count IS NULL
    )
    OR
    (
      operation = 'mfa_confirm'
      AND secret_ref IS NULL
      AND secret_digest IS NULL
      AND expected_recovery_batch_digest IS NULL
      AND expected_recovery_code_count IS NULL
      AND a1_identity_digest_valid(recovery_batch_digest)
      AND recovery_code_count BETWEEN 6 AND 20
    )
    OR
    (
      operation = 'mfa_recovery_consume'
      AND secret_ref IS NOT NULL
      AND length(secret_ref) >= 16
      AND a1_identity_digest_valid(secret_digest)
      AND a1_identity_digest_valid(expected_recovery_batch_digest)
      AND expected_recovery_code_count BETWEEN 1 AND 20
      AND a1_identity_digest_valid(recovery_batch_digest)
      AND recovery_code_count = expected_recovery_code_count - 1
    )
    OR
    (
      operation = 'mfa_recovery_rotate'
      AND secret_ref IS NOT NULL
      AND length(secret_ref) >= 16
      AND a1_identity_digest_valid(secret_digest)
      AND a1_identity_digest_valid(expected_recovery_batch_digest)
      AND expected_recovery_code_count BETWEEN 0 AND 20
      AND a1_identity_digest_valid(recovery_batch_digest)
      AND recovery_code_count BETWEEN 6 AND 20
    )
    OR
    (
      operation = 'mfa_disable'
      AND secret_ref IS NOT NULL
      AND length(secret_ref) >= 16
      AND a1_identity_digest_valid(secret_digest)
      AND a1_identity_digest_valid(expected_recovery_batch_digest)
      AND expected_recovery_code_count BETWEEN 0 AND 20
      AND recovery_batch_digest IS NULL
      AND recovery_code_count = 0
    )
    OR
    (
      operation = 'credential_bind'
      AND secret_ref IS NULL
      AND secret_digest IS NULL
      AND expected_recovery_batch_digest IS NULL
      AND expected_recovery_code_count IS NULL
      AND recovery_batch_digest IS NULL
      AND recovery_code_count IS NULL
    )
  );

ALTER TABLE identity_security_mutation_idempotency
  DROP CONSTRAINT IF EXISTS identity_security_mutation_idempotency_operation_check;
ALTER TABLE identity_security_mutation_idempotency
  ADD CONSTRAINT identity_security_mutation_idempotency_operation_check CHECK (
    operation IN (
      'password_enroll','password_change','password_recovery',
      'mfa_enroll','mfa_confirm','mfa_recovery_consume',
      'mfa_recovery_rotate','mfa_disable','credential_bind'
    )
  );

ALTER TABLE identity_security_ticket_issuance
  DROP CONSTRAINT IF EXISTS identity_security_ticket_issuance_operation_check;
ALTER TABLE identity_security_ticket_issuance
  ADD CONSTRAINT identity_security_ticket_issuance_operation_check CHECK (
    operation IN (
      'password_enroll','password_change','password_recovery',
      'mfa_enroll','mfa_confirm','mfa_recovery_consume',
      'mfa_recovery_rotate','mfa_disable','credential_bind'
    )
  );

-- Confirming enrollment clears the pending timestamp so every TOTP posture has
-- one unambiguous state shape.
CREATE OR REPLACE FUNCTION a1_confirm_totp_enrollment(
  p_principal_id UUID,
  p_receipt_digest TEXT,
  p_context_digest TEXT,
  p_recovery_batch_digest TEXT,
  p_recovery_code_count INTEGER,
  p_now TIMESTAMPTZ
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp
AS $$
DECLARE
  v_revoked BIGINT;
  v_version BIGINT;
BEGIN
  IF p_recovery_code_count NOT BETWEEN 6 AND 20
     OR NOT a1_identity_digest_valid(p_recovery_batch_digest)
     OR NOT a1_consume_identity_security_receipt(
       p_receipt_digest,
       p_principal_id,
       'mfa_confirm',
       p_context_digest,
       p_now
     ) THEN
    RAISE EXCEPTION 'mfa_confirmation_rejected' USING ERRCODE='42501';
  END IF;

  UPDATE identity_account_security
     SET two_factor_status='enabled',
         two_factor_enrolled_at=p_now,
         totp_pending_at=NULL,
         recovery_code_batch_digest=p_recovery_batch_digest,
         recovery_codes_remaining=p_recovery_code_count,
         security_version=security_version+1,
         updated_at=p_now
   WHERE principal_id=p_principal_id
     AND two_factor_status='pending'
     AND totp_pending_at>p_now-INTERVAL '15 minutes'
  RETURNING security_version INTO v_version;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'mfa_enrollment_unavailable' USING ERRCODE='55000';
  END IF;

  UPDATE identity_sessions
     SET status='revoked',
         revoked_at=p_now,
         revoke_reason_code='mfa_enabled'
   WHERE principal_id=p_principal_id
     AND status='active';
  GET DIAGNOSTICS v_revoked=ROW_COUNT;

  PERFORM a1_identity_write_event(
    p_principal_id,
    NULL,
    NULL,
    p_principal_id,
    'identity.mfa_confirm',
    'principal',
    p_principal_id,
    p_context_digest,
    jsonb_build_object(
      'security_version',v_version,
      'sessions_revoked',v_revoked,
      'recovery_codes_remaining',p_recovery_code_count,
      'outcome','success'
    )
  );
  RETURN jsonb_build_object(
    'two_factor_status','enabled',
    'recovery_codes_remaining',p_recovery_code_count,
    'security_version',v_version,
    'sessions_revoked',v_revoked,
    'reauthentication_required',TRUE
  );
END
$$;

DROP FUNCTION IF EXISTS a1_issue_identity_security_mutation_ticket(
  TEXT,TEXT,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TIMESTAMPTZ
);
DROP FUNCTION IF EXISTS a1_issue_identity_security_mutation_ticket(
  TEXT,TEXT,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,INTEGER,TIMESTAMPTZ
);
CREATE FUNCTION a1_issue_identity_security_mutation_ticket(
  p_ticket_digest TEXT,
  p_step_up_receipt_digest TEXT,
  p_principal_id UUID,
  p_actor_principal_id UUID,
  p_operation TEXT,
  p_context_digest TEXT,
  p_secret_ref TEXT,
  p_secret_digest TEXT,
  p_expected_recovery_batch_digest TEXT,
  p_expected_recovery_code_count INTEGER,
  p_recovery_batch_digest TEXT,
  p_recovery_code_count INTEGER,
  p_expires_at TIMESTAMPTZ
) RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp
AS $$
DECLARE
  v_receipt identity_security_receipts%ROWTYPE;
  v_existing identity_security_mutation_tickets%ROWTYPE;
  v_now CONSTANT TIMESTAMPTZ := clock_timestamp();
BEGIN
  IF NOT a1_identity_digest_valid(p_ticket_digest)
     OR p_actor_principal_id IS DISTINCT FROM p_principal_id
     OR p_operation NOT IN (
       'password_enroll','password_change','password_recovery',
       'mfa_enroll','mfa_confirm','mfa_recovery_consume',
       'mfa_recovery_rotate','mfa_disable','credential_bind'
     )
     OR NOT a1_identity_digest_valid(p_context_digest)
     OR p_expires_at IS NULL
     OR p_expires_at<=v_now THEN
    RAISE EXCEPTION 'identity_security_ticket_rejected'
      USING ERRCODE='42501';
  END IF;

  SELECT *
    INTO v_existing
    FROM identity_security_mutation_tickets
   WHERE ticket_digest=p_ticket_digest
   FOR UPDATE;
  IF FOUND THEN
    IF v_existing.step_up_receipt_digest
         IS NOT DISTINCT FROM p_step_up_receipt_digest
       AND v_existing.principal_id IS NOT DISTINCT FROM p_principal_id
       AND v_existing.actor_principal_id
         IS NOT DISTINCT FROM p_actor_principal_id
       AND v_existing.operation IS NOT DISTINCT FROM p_operation
       AND v_existing.context_digest IS NOT DISTINCT FROM p_context_digest
       AND v_existing.secret_ref IS NOT DISTINCT FROM p_secret_ref
       AND v_existing.secret_digest IS NOT DISTINCT FROM p_secret_digest
       AND v_existing.expected_recovery_batch_digest
         IS NOT DISTINCT FROM p_expected_recovery_batch_digest
       AND v_existing.expected_recovery_code_count
         IS NOT DISTINCT FROM p_expected_recovery_code_count
       AND v_existing.recovery_batch_digest
         IS NOT DISTINCT FROM p_recovery_batch_digest
       AND v_existing.recovery_code_count
         IS NOT DISTINCT FROM p_recovery_code_count
       AND v_existing.expires_at IS NOT DISTINCT FROM p_expires_at THEN
      RETURN TRUE;
    END IF;
    RAISE EXCEPTION 'identity_security_ticket_issuance_conflict'
      USING ERRCODE='23505';
  END IF;

  SELECT *
    INTO v_receipt
    FROM identity_security_receipts
   WHERE receipt_digest=p_step_up_receipt_digest
     AND principal_id=p_principal_id
     AND purpose=p_operation
     AND context_digest=p_context_digest
     AND consumed_at IS NULL
     AND expires_at>v_now
   FOR UPDATE;
  IF NOT FOUND OR p_expires_at>v_receipt.expires_at THEN
    RAISE EXCEPTION 'identity_security_ticket_receipt_rejected'
      USING ERRCODE='42501';
  END IF;

  -- The receipt lock may have allowed an exact concurrent retry to finish.
  SELECT *
    INTO v_existing
    FROM identity_security_mutation_tickets
   WHERE ticket_digest=p_ticket_digest
   FOR UPDATE;
  IF FOUND THEN
    IF v_existing.step_up_receipt_digest
         IS NOT DISTINCT FROM p_step_up_receipt_digest
       AND v_existing.principal_id IS NOT DISTINCT FROM p_principal_id
       AND v_existing.actor_principal_id
         IS NOT DISTINCT FROM p_actor_principal_id
       AND v_existing.operation IS NOT DISTINCT FROM p_operation
       AND v_existing.context_digest IS NOT DISTINCT FROM p_context_digest
       AND v_existing.secret_ref IS NOT DISTINCT FROM p_secret_ref
       AND v_existing.secret_digest IS NOT DISTINCT FROM p_secret_digest
       AND v_existing.expected_recovery_batch_digest
         IS NOT DISTINCT FROM p_expected_recovery_batch_digest
       AND v_existing.expected_recovery_code_count
         IS NOT DISTINCT FROM p_expected_recovery_code_count
       AND v_existing.recovery_batch_digest
         IS NOT DISTINCT FROM p_recovery_batch_digest
       AND v_existing.recovery_code_count
         IS NOT DISTINCT FROM p_recovery_code_count
       AND v_existing.expires_at IS NOT DISTINCT FROM p_expires_at THEN
      RETURN TRUE;
    END IF;
    RAISE EXCEPTION 'identity_security_ticket_issuance_conflict'
      USING ERRCODE='23505';
  END IF;

  PERFORM 1
    FROM identity_security_mutation_tickets
   WHERE step_up_receipt_digest=p_step_up_receipt_digest
   FOR UPDATE;
  IF FOUND THEN
    RAISE EXCEPTION 'identity_security_receipt_ticket_conflict'
      USING ERRCODE='23505';
  END IF;

  INSERT INTO identity_security_mutation_tickets(
    ticket_digest,
    step_up_receipt_digest,
    principal_id,
    actor_principal_id,
    operation,
    context_digest,
    secret_ref,
    secret_digest,
    expected_recovery_batch_digest,
    expected_recovery_code_count,
    recovery_batch_digest,
    recovery_code_count,
    expires_at,
    created_at
  ) VALUES (
    p_ticket_digest,
    p_step_up_receipt_digest,
    p_principal_id,
    p_actor_principal_id,
    p_operation,
    p_context_digest,
    p_secret_ref,
    p_secret_digest,
    p_expected_recovery_batch_digest,
    p_expected_recovery_code_count,
    p_recovery_batch_digest,
    p_recovery_code_count,
    p_expires_at,
    v_now
  );
  RETURN TRUE;
END
$$;

CREATE OR REPLACE FUNCTION a1_mutate_totp_recovery_lifecycle(
  p_principal_id UUID,
  p_operation TEXT,
  p_secret_ref TEXT,
  p_secret_digest TEXT,
  p_expected_recovery_batch_digest TEXT,
  p_expected_recovery_code_count INTEGER,
  p_recovery_batch_digest TEXT,
  p_recovery_code_count INTEGER,
  p_receipt_digest TEXT,
  p_context_digest TEXT,
  p_actor_principal_id UUID,
  p_request_digest TEXT,
  p_now TIMESTAMPTZ
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp
AS $$
DECLARE
  v_security identity_account_security%ROWTYPE;
  v_issuance identity_security_ticket_issuance%ROWTYPE;
  v_revoked BIGINT;
  v_version BIGINT;
  v_event_type TEXT;
BEGIN
  IF p_actor_principal_id IS DISTINCT FROM p_principal_id
     OR p_operation NOT IN (
       'mfa_recovery_consume','mfa_recovery_rotate','mfa_disable'
     )
     OR length(p_secret_ref)<16
     OR NOT a1_identity_digest_valid(p_secret_digest)
     OR NOT a1_identity_digest_valid(p_expected_recovery_batch_digest)
     OR p_expected_recovery_code_count NOT BETWEEN 0 AND 20
     OR NOT a1_identity_digest_valid(p_request_digest) THEN
    RAISE EXCEPTION 'identity_totp_recovery_mutation_rejected'
      USING ERRCODE='42501';
  END IF;
  IF p_operation='mfa_recovery_consume' AND (
       p_expected_recovery_code_count NOT BETWEEN 1 AND 20
       OR NOT a1_identity_digest_valid(p_recovery_batch_digest)
       OR p_recovery_code_count<>p_expected_recovery_code_count-1
     ) THEN
    RAISE EXCEPTION 'identity_totp_recovery_mutation_rejected'
      USING ERRCODE='42501';
  ELSIF p_operation='mfa_recovery_rotate' AND (
       NOT a1_identity_digest_valid(p_recovery_batch_digest)
       OR p_recovery_code_count NOT BETWEEN 6 AND 20
     ) THEN
    RAISE EXCEPTION 'identity_totp_recovery_mutation_rejected'
      USING ERRCODE='42501';
  ELSIF p_operation='mfa_disable' AND (
       p_recovery_batch_digest IS NOT NULL
       OR p_recovery_code_count<>0
     ) THEN
    RAISE EXCEPTION 'identity_totp_recovery_mutation_rejected'
      USING ERRCODE='42501';
  END IF;

  SELECT *
    INTO v_security
    FROM identity_account_security
   WHERE principal_id=p_principal_id
   FOR UPDATE;
  IF NOT FOUND
     OR v_security.two_factor_status<>'enabled'
     OR v_security.totp_secret_ref IS DISTINCT FROM p_secret_ref
     OR v_security.totp_secret_digest IS DISTINCT FROM p_secret_digest
     OR v_security.recovery_code_batch_digest
          IS DISTINCT FROM p_expected_recovery_batch_digest
     OR v_security.recovery_codes_remaining
          IS DISTINCT FROM p_expected_recovery_code_count THEN
    RAISE EXCEPTION 'identity_totp_recovery_state_stale'
      USING ERRCODE='40001';
  END IF;

  SELECT issuance.*
    INTO v_issuance
    FROM identity_security_ticket_issuance AS issuance
    JOIN identity_security_mutation_tickets AS ticket
      ON ticket.ticket_digest=issuance.ticket_digest
   WHERE ticket.step_up_receipt_digest=p_receipt_digest
     AND ticket.principal_id=p_principal_id
     AND ticket.operation=p_operation
     AND issuance.actor_principal_id=p_actor_principal_id
     AND issuance.context_digest=p_context_digest
     AND issuance.canceled_at IS NULL
   FOR UPDATE OF issuance;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity_totp_recovery_scope_rejected'
      USING ERRCODE='42501';
  END IF;

  IF NOT a1_consume_identity_security_receipt(
    p_receipt_digest,
    p_principal_id,
    p_operation,
    p_context_digest,
    p_now
  ) THEN
    RAISE EXCEPTION 'identity_totp_recovery_receipt_unavailable'
      USING ERRCODE='42501';
  END IF;

  IF p_operation='mfa_disable' THEN
    UPDATE identity_account_security
       SET two_factor_status='disabled',
           totp_secret_ref=NULL,
           totp_secret_digest=NULL,
           totp_pending_at=NULL,
           two_factor_enrolled_at=NULL,
           recovery_code_batch_digest=NULL,
           recovery_codes_remaining=0,
           security_version=security_version+1,
           updated_at=p_now
     WHERE principal_id=p_principal_id
    RETURNING security_version INTO v_version;
    v_event_type := 'identity.mfa_disable';
  ELSE
    UPDATE identity_account_security
       SET recovery_code_batch_digest=p_recovery_batch_digest,
           recovery_codes_remaining=p_recovery_code_count,
           security_version=security_version+1,
           updated_at=p_now
     WHERE principal_id=p_principal_id
    RETURNING security_version INTO v_version;
    IF p_operation='mfa_recovery_consume' THEN
      v_event_type := 'identity.mfa_recovery_consume';
    ELSE
      v_event_type := 'identity.mfa_recovery_rotate';
    END IF;
  END IF;

  UPDATE identity_sessions
     SET status='revoked',
         revoked_at=p_now,
         revoke_reason_code=p_operation
   WHERE principal_id=p_principal_id
     AND status='active';
  GET DIAGNOSTICS v_revoked=ROW_COUNT;

  PERFORM a1_identity_write_event(
    p_principal_id,
    v_issuance.organization_id,
    v_issuance.project_id,
    p_actor_principal_id,
    v_event_type,
    'principal',
    p_principal_id,
    p_request_digest,
    jsonb_build_object(
      'security_version',v_version,
      'sessions_revoked',v_revoked,
      'recovery_codes_remaining',p_recovery_code_count,
      'outcome','success'
    )
  );
  RETURN jsonb_build_object(
    'two_factor_status',
      CASE WHEN p_operation='mfa_disable' THEN 'disabled' ELSE 'enabled' END,
    'recovery_codes_remaining',p_recovery_code_count,
    'security_version',v_version,
    'sessions_revoked',v_revoked,
    'reauthentication_required',TRUE
  );
END
$$;

CREATE OR REPLACE FUNCTION a1_execute_identity_security_mutation(
  p_ticket_digest TEXT,
  p_idempotency_key TEXT,
  p_request_fingerprint TEXT
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp
AS $$
DECLARE
  v_ticket identity_security_mutation_tickets%ROWTYPE;
  v_idempotency identity_security_mutation_idempotency%ROWTYPE;
  v_result JSONB;
  v_now CONSTANT TIMESTAMPTZ := clock_timestamp();
BEGIN
  IF NOT a1_identity_digest_valid(p_ticket_digest)
     OR length(p_idempotency_key) NOT BETWEEN 8 AND 255
     OR p_idempotency_key !~ '^[A-Za-z0-9._:-]+$'
     OR NOT a1_identity_digest_valid(p_request_fingerprint) THEN
    RAISE EXCEPTION 'identity_security_mutation_rejected'
      USING ERRCODE='42501';
  END IF;

  SELECT *
    INTO v_ticket
    FROM identity_security_mutation_tickets
   WHERE ticket_digest=p_ticket_digest
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity_security_ticket_unavailable'
      USING ERRCODE='42501';
  END IF;

  INSERT INTO identity_security_mutation_idempotency(
    principal_id,
    operation,
    idempotency_key,
    ticket_digest,
    request_fingerprint,
    created_at
  ) VALUES (
    v_ticket.principal_id,
    v_ticket.operation,
    p_idempotency_key,
    p_ticket_digest,
    p_request_fingerprint,
    v_now
  )
  ON CONFLICT (principal_id,operation,idempotency_key) DO NOTHING;

  SELECT *
    INTO v_idempotency
    FROM identity_security_mutation_idempotency
   WHERE principal_id=v_ticket.principal_id
     AND operation=v_ticket.operation
     AND idempotency_key=p_idempotency_key
   FOR UPDATE;
  IF v_idempotency.ticket_digest<>p_ticket_digest
     OR v_idempotency.request_fingerprint<>p_request_fingerprint THEN
    RAISE EXCEPTION 'identity_security_idempotency_conflict'
      USING ERRCODE='23505';
  END IF;
  IF v_idempotency.result_json IS NOT NULL THEN
    RETURN v_idempotency.result_json;
  END IF;

  IF v_ticket.consumed_at IS NOT NULL OR v_ticket.expires_at<=v_now THEN
    RAISE EXCEPTION 'identity_security_ticket_expired_or_consumed'
      USING ERRCODE='42501';
  END IF;
  UPDATE identity_security_mutation_tickets
     SET consumed_at=v_now
   WHERE ticket_digest=p_ticket_digest;

  IF v_ticket.operation IN (
    'password_enroll','password_change','password_recovery'
  ) THEN
    v_result := a1_mutate_account_password(
      v_ticket.principal_id,
      v_ticket.operation,
      v_ticket.secret_ref,
      v_ticket.secret_digest,
      v_ticket.step_up_receipt_digest,
      v_ticket.context_digest,
      v_ticket.actor_principal_id,
      v_now
    );
  ELSIF v_ticket.operation='mfa_enroll' THEN
    v_result := a1_begin_totp_enrollment(
      v_ticket.principal_id,
      v_ticket.secret_ref,
      v_ticket.secret_digest,
      v_ticket.step_up_receipt_digest,
      v_ticket.context_digest,
      v_ticket.actor_principal_id,
      v_now
    );
  ELSIF v_ticket.operation='mfa_confirm' THEN
    v_result := a1_confirm_totp_enrollment(
      v_ticket.principal_id,
      v_ticket.step_up_receipt_digest,
      v_ticket.context_digest,
      v_ticket.recovery_batch_digest,
      v_ticket.recovery_code_count,
      v_now
    );
  ELSIF v_ticket.operation IN (
    'mfa_recovery_consume','mfa_recovery_rotate','mfa_disable'
  ) THEN
    v_result := a1_mutate_totp_recovery_lifecycle(
      v_ticket.principal_id,
      v_ticket.operation,
      v_ticket.secret_ref,
      v_ticket.secret_digest,
      v_ticket.expected_recovery_batch_digest,
      v_ticket.expected_recovery_code_count,
      v_ticket.recovery_batch_digest,
      v_ticket.recovery_code_count,
      v_ticket.step_up_receipt_digest,
      v_ticket.context_digest,
      v_ticket.actor_principal_id,
      p_request_fingerprint,
      v_now
    );
  ELSE
    RAISE EXCEPTION 'identity_security_operation_unsupported'
      USING ERRCODE='0A000';
  END IF;

  UPDATE identity_security_mutation_idempotency
     SET result_json=v_result,
         completed_at=v_now
   WHERE principal_id=v_ticket.principal_id
     AND operation=v_ticket.operation
     AND idempotency_key=p_idempotency_key;
  RETURN v_result;
END
$$;

CREATE OR REPLACE FUNCTION a1_resolve_identity_security_mutation_ticket(
  p_ticket_digest TEXT,
  p_step_up_receipt_digest TEXT,
  p_operation TEXT,
  p_now TIMESTAMPTZ
) RETURNS JSONB
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp
AS $$
DECLARE
  v_ticket identity_security_mutation_tickets%ROWTYPE;
BEGIN
  IF NOT a1_identity_digest_valid(p_ticket_digest)
     OR NOT a1_identity_digest_valid(p_step_up_receipt_digest)
     OR p_operation NOT IN (
       'password_enroll','password_change','password_recovery',
       'mfa_enroll','mfa_confirm','mfa_recovery_consume',
       'mfa_recovery_rotate','mfa_disable','credential_bind'
     ) THEN
    RAISE EXCEPTION 'identity_security_ticket_rejected'
      USING ERRCODE='42501';
  END IF;

  SELECT *
    INTO v_ticket
    FROM identity_security_mutation_tickets
   WHERE ticket_digest=p_ticket_digest
     AND step_up_receipt_digest=p_step_up_receipt_digest
     AND operation=p_operation;
  IF NOT FOUND
     OR v_ticket.expires_at<=p_now
     OR (
       v_ticket.consumed_at IS NOT NULL
       AND p_operation<>'credential_bind'
     ) THEN
    RAISE EXCEPTION 'identity_security_ticket_unavailable'
      USING ERRCODE='42501';
  END IF;

  RETURN jsonb_build_object(
    'ticket_id',v_ticket.ticket_digest,
    'account_id',v_ticket.principal_id,
    'operation',v_ticket.operation,
    'step_up_receipt_id',v_ticket.step_up_receipt_digest,
    'expires_at',v_ticket.expires_at
  );
END
$$;

-- Private processor projection: secret references and keyed digests are
-- available only to the restricted runtime role inside a principal-scoped
-- transaction.
CREATE OR REPLACE FUNCTION a1_project_identity_security_processor_state(
  p_principal_id UUID
) RETURNS JSONB
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp
AS $$
DECLARE
  v_projection JSONB;
BEGIN
  IF p_principal_id IS NULL
     OR a1_current_principal_id() IS DISTINCT FROM p_principal_id THEN
    RAISE EXCEPTION 'identity_security_principal_scope_rejected'
      USING ERRCODE='42501';
  END IF;

  SELECT jsonb_build_object(
    'two_factor_status',security.two_factor_status,
    'totp_secret_ref',security.totp_secret_ref,
    'totp_secret_digest',security.totp_secret_digest,
    'recovery_batch_digest',security.recovery_code_batch_digest,
    'recovery_codes_remaining',security.recovery_codes_remaining
  )
    INTO v_projection
    FROM identity_account_security AS security
   WHERE security.principal_id=p_principal_id;
  RETURN v_projection;
END
$$;

-- Private committed replay contains only the non-plaintext processor envelope
-- and the already-public SQL result. It deliberately excludes receipts,
-- ticket digests, finalize/cleanup/handoff tokens and raw recovery codes.
CREATE OR REPLACE FUNCTION a1_project_identity_security_mutation_replay(
  p_principal_id UUID,
  p_operation TEXT,
  p_idempotency_key TEXT
) RETURNS JSONB
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp
AS $$
DECLARE
  v_projection JSONB;
BEGIN
  IF p_principal_id IS NULL
     OR a1_current_principal_id() IS DISTINCT FROM p_principal_id
     OR p_operation NOT IN (
       'mfa_recovery_consume','mfa_recovery_rotate','mfa_disable'
     )
     OR length(p_idempotency_key) NOT BETWEEN 8 AND 255
     OR p_idempotency_key !~ '^[A-Za-z0-9._:-]+$' THEN
    RAISE EXCEPTION 'identity_security_replay_scope_rejected'
      USING ERRCODE='42501';
  END IF;

  SELECT jsonb_build_object(
    'secret_ref',ticket.secret_ref,
    'secret_digest',ticket.secret_digest,
    'expected_recovery_batch_digest',
      ticket.expected_recovery_batch_digest,
    'expected_recovery_code_count',
      ticket.expected_recovery_code_count,
    'recovery_batch_digest',ticket.recovery_batch_digest,
    'recovery_code_count',ticket.recovery_code_count,
    'result',replay.result_json
  )
    INTO v_projection
    FROM identity_security_mutation_idempotency AS replay
    JOIN identity_security_mutation_tickets AS ticket
      ON ticket.ticket_digest=replay.ticket_digest
     AND ticket.principal_id=replay.principal_id
     AND ticket.operation=replay.operation
   WHERE replay.principal_id=p_principal_id
     AND replay.operation=p_operation
     AND replay.idempotency_key=p_idempotency_key
     AND replay.result_json IS NOT NULL
     AND replay.completed_at IS NOT NULL;
  RETURN v_projection;
END
$$;

DROP FUNCTION IF EXISTS a1_issue_scoped_identity_security_mutation_ticket(
  UUID,UUID,UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TIMESTAMPTZ
);
DROP FUNCTION IF EXISTS a1_issue_scoped_identity_security_mutation_ticket(
  UUID,UUID,UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,INTEGER,TIMESTAMPTZ
);
CREATE FUNCTION a1_issue_scoped_identity_security_mutation_ticket(
  p_organization_id UUID,
  p_project_id UUID,
  p_principal_id UUID,
  p_actor_principal_id UUID,
  p_recent_session_id UUID,
  p_session_digest TEXT,
  p_operation TEXT,
  p_issuer_idempotency_key TEXT,
  p_context_digest TEXT,
  p_secret_ref TEXT,
  p_secret_digest TEXT,
  p_expected_recovery_batch_digest TEXT,
  p_expected_recovery_code_count INTEGER,
  p_recovery_batch_digest TEXT,
  p_recovery_code_count INTEGER,
  p_expires_at TIMESTAMPTZ
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp
AS $$
DECLARE
  v_now CONSTANT TIMESTAMPTZ := clock_timestamp();
  v_expected_context_digest TEXT;
  v_recent_session_id UUID;
  v_existing identity_security_ticket_issuance%ROWTYPE;
  v_existing_ticket identity_security_mutation_tickets%ROWTYPE;
  v_ticket_digest TEXT;
  v_receipt_digest TEXT;
  v_expected_digest TEXT;
  v_expected_count INTEGER;
  v_recovery_digest TEXT;
  v_recovery_count INTEGER;
BEGIN
  IF current_setting('role', TRUE) <> 'a1_security_ticket_issuer'
     OR NOT pg_has_role(
       session_user,
       'a1_security_ticket_issuer',
       'MEMBER'
     ) THEN
    RAISE EXCEPTION 'identity_security_ticket_issuer_role_rejected'
      USING ERRCODE='42501';
  END IF;
  PERFORM a1_assert_role_nobypassrls('a1_security_ticket_issuer');
  PERFORM a1_assert_role_nobypassrls(session_user);

  IF p_principal_id IS NULL
     OR p_actor_principal_id IS DISTINCT FROM p_principal_id
     OR a1_current_principal_id() IS DISTINCT FROM p_principal_id
     OR p_recent_session_id IS NULL
     OR NOT a1_identity_digest_valid(p_session_digest)
     OR p_operation NOT IN (
       'password_enroll','password_change','password_recovery',
       'mfa_enroll','mfa_confirm','mfa_recovery_consume',
       'mfa_recovery_rotate','mfa_disable'
     )
     OR length(p_issuer_idempotency_key) NOT BETWEEN 8 AND 255
     OR p_issuer_idempotency_key !~ '^[A-Za-z0-9._:-]+$'
     OR NOT a1_identity_digest_valid(p_context_digest)
     OR p_expires_at IS NULL
     OR p_expires_at<=v_now
     OR p_expires_at>v_now+INTERVAL '5 minutes' THEN
    RAISE EXCEPTION 'identity_security_ticket_scope_rejected'
      USING ERRCODE='42501';
  END IF;

  IF p_operation IN (
    'password_enroll','password_change','password_recovery','mfa_enroll'
  ) THEN
    IF length(p_secret_ref)<16
       OR NOT a1_identity_digest_valid(p_secret_digest)
       OR p_expected_recovery_batch_digest IS NOT NULL
       OR COALESCE(p_expected_recovery_code_count,0)<>0
       OR p_recovery_batch_digest IS NOT NULL
       OR COALESCE(p_recovery_code_count,0)<>0 THEN
      RAISE EXCEPTION 'identity_security_ticket_payload_rejected'
        USING ERRCODE='42501';
    END IF;
    v_expected_digest := NULL;
    v_expected_count := NULL;
    v_recovery_digest := NULL;
    v_recovery_count := NULL;
  ELSIF p_operation='mfa_confirm' THEN
    IF p_secret_ref IS NOT NULL
       OR p_secret_digest IS NOT NULL
       OR p_expected_recovery_batch_digest IS NOT NULL
       OR COALESCE(p_expected_recovery_code_count,0)<>0
       OR NOT a1_identity_digest_valid(p_recovery_batch_digest)
       OR p_recovery_code_count NOT BETWEEN 6 AND 20 THEN
      RAISE EXCEPTION 'identity_security_ticket_payload_rejected'
        USING ERRCODE='42501';
    END IF;
    v_expected_digest := NULL;
    v_expected_count := NULL;
    v_recovery_digest := p_recovery_batch_digest;
    v_recovery_count := p_recovery_code_count;
  ELSE
    IF length(p_secret_ref)<16
       OR NOT a1_identity_digest_valid(p_secret_digest)
       OR NOT a1_identity_digest_valid(
         p_expected_recovery_batch_digest
       )
       OR p_expected_recovery_code_count NOT BETWEEN 0 AND 20 THEN
      RAISE EXCEPTION 'identity_security_ticket_payload_rejected'
        USING ERRCODE='42501';
    END IF;
    IF p_operation='mfa_recovery_consume' AND (
         p_expected_recovery_code_count NOT BETWEEN 1 AND 20
         OR NOT a1_identity_digest_valid(p_recovery_batch_digest)
         OR p_recovery_code_count<>p_expected_recovery_code_count-1
       ) THEN
      RAISE EXCEPTION 'identity_security_ticket_payload_rejected'
        USING ERRCODE='42501';
    ELSIF p_operation='mfa_recovery_rotate' AND (
         NOT a1_identity_digest_valid(p_recovery_batch_digest)
         OR p_recovery_code_count NOT BETWEEN 6 AND 20
       ) THEN
      RAISE EXCEPTION 'identity_security_ticket_payload_rejected'
        USING ERRCODE='42501';
    ELSIF p_operation='mfa_disable' AND (
         p_recovery_batch_digest IS NOT NULL
         OR p_recovery_code_count<>0
       ) THEN
      RAISE EXCEPTION 'identity_security_ticket_payload_rejected'
        USING ERRCODE='42501';
    END IF;
    v_expected_digest := p_expected_recovery_batch_digest;
    v_expected_count := p_expected_recovery_code_count;
    v_recovery_digest := p_recovery_batch_digest;
    v_recovery_count := p_recovery_code_count;
  END IF;

  v_expected_context_digest := encode(
    digest(
      convert_to('ashr.identity_security_ticket.v1','UTF8')
      || decode('00','hex')
      || convert_to(p_organization_id::TEXT,'UTF8')
      || decode('00','hex')
      || convert_to(p_project_id::TEXT,'UTF8')
      || decode('00','hex')
      || convert_to(p_principal_id::TEXT,'UTF8')
      || decode('00','hex')
      || convert_to(p_actor_principal_id::TEXT,'UTF8')
      || decode('00','hex')
      || convert_to(p_recent_session_id::TEXT,'UTF8')
      || decode('00','hex')
      || convert_to(p_session_digest,'UTF8')
      || decode('00','hex')
      || convert_to(p_operation,'UTF8')
      || decode('00','hex')
      || convert_to(p_issuer_idempotency_key,'UTF8'),
      'sha256'
    ),
    'hex'
  );
  IF v_expected_context_digest IS DISTINCT FROM p_context_digest THEN
    RAISE EXCEPTION 'identity_security_ticket_context_rejected'
      USING ERRCODE='42501';
  END IF;

  v_recent_session_id := a1_assert_recent_identity_authentication(
    p_organization_id,
    p_project_id,
    p_principal_id,
    p_session_digest,
    600,
    'aal1'
  );
  IF v_recent_session_id IS DISTINCT FROM p_recent_session_id THEN
    RAISE EXCEPTION 'identity_security_ticket_session_rejected'
      USING ERRCODE='42501';
  END IF;
  IF p_operation='password_recovery'
     AND NOT EXISTS (
       SELECT 1
         FROM identity_sessions AS recent_session
         JOIN identity_credentials AS recovery_credential
           ON recovery_credential.principal_id=recent_session.principal_id
          AND recovery_credential.id=recent_session.credential_id
          AND recovery_credential.provider='email'
          AND recovery_credential.credential_kind IN (
            'email_otp','email_password'
          )
          AND recovery_credential.status='active'
          AND recovery_credential.login_enabled
          AND recovery_credential.verified_at IS NOT NULL
        WHERE recent_session.id=p_recent_session_id
          AND recent_session.principal_id=p_principal_id
     ) THEN
    RAISE EXCEPTION 'identity_security_recovery_credential_rejected'
      USING ERRCODE='42501';
  END IF;

  PERFORM 1
    FROM identity_principals
   WHERE id=p_principal_id
     AND status='active'
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity_security_ticket_principal_rejected'
      USING ERRCODE='42501';
  END IF;

  SELECT *
    INTO v_existing
    FROM identity_security_ticket_issuance
   WHERE principal_id=p_principal_id
     AND operation=p_operation
     AND issuer_idempotency_key=p_issuer_idempotency_key
   FOR UPDATE;
  IF FOUND THEN
    SELECT *
      INTO v_existing_ticket
      FROM identity_security_mutation_tickets
     WHERE ticket_digest=v_existing.ticket_digest
     FOR UPDATE;
    IF NOT FOUND
       OR v_existing.organization_id IS DISTINCT FROM p_organization_id
       OR v_existing.project_id IS DISTINCT FROM p_project_id
       OR v_existing.actor_principal_id
            IS DISTINCT FROM p_actor_principal_id
       OR v_existing.recent_session_id
            IS DISTINCT FROM p_recent_session_id
       OR v_existing.context_digest IS DISTINCT FROM p_context_digest
       OR v_existing.canceled_at IS NOT NULL
       OR v_existing_ticket.secret_ref IS DISTINCT FROM p_secret_ref
       OR v_existing_ticket.secret_digest IS DISTINCT FROM p_secret_digest
       OR v_existing_ticket.expected_recovery_batch_digest
            IS DISTINCT FROM v_expected_digest
       OR v_existing_ticket.expected_recovery_code_count
            IS DISTINCT FROM v_expected_count
       OR v_existing_ticket.recovery_batch_digest
            IS DISTINCT FROM v_recovery_digest
       OR v_existing_ticket.recovery_code_count
            IS DISTINCT FROM v_recovery_count THEN
      RAISE EXCEPTION 'identity_security_ticket_idempotency_conflict'
        USING ERRCODE='23505';
    END IF;
    RETURN jsonb_build_object(
      'ticket_id',v_existing.ticket_digest,
      'step_up_receipt_id',v_existing.step_up_receipt_digest,
      'context_digest',v_existing.context_digest,
      'expires_at',v_existing.expires_at
    );
  END IF;

  v_receipt_digest := encode(
    digest(
      gen_random_bytes(32)
      || convert_to('ashr.identity_security.receipt.v1','UTF8')
      || convert_to(p_context_digest,'UTF8'),
      'sha256'
    ),
    'hex'
  );
  v_ticket_digest := encode(
    digest(
      gen_random_bytes(32)
      || convert_to('ashr.identity_security.ticket.v1','UTF8')
      || convert_to(p_context_digest,'UTF8'),
      'sha256'
    ),
    'hex'
  );

  INSERT INTO identity_security_receipts(
    receipt_digest,
    principal_id,
    purpose,
    context_digest,
    expires_at,
    created_at
  ) VALUES (
    v_receipt_digest,
    p_principal_id,
    p_operation,
    p_context_digest,
    p_expires_at,
    v_now
  );

  IF NOT a1_issue_identity_security_mutation_ticket(
    v_ticket_digest,
    v_receipt_digest,
    p_principal_id,
    p_actor_principal_id,
    p_operation,
    p_context_digest,
    p_secret_ref,
    p_secret_digest,
    v_expected_digest,
    v_expected_count,
    v_recovery_digest,
    v_recovery_count,
    p_expires_at
  ) THEN
    RAISE EXCEPTION 'identity_security_ticket_issuance_rejected'
      USING ERRCODE='42501';
  END IF;

  INSERT INTO identity_security_ticket_issuance(
    organization_id,
    project_id,
    principal_id,
    actor_principal_id,
    recent_session_id,
    operation,
    context_digest,
    issuer_idempotency_key,
    ticket_digest,
    step_up_receipt_digest,
    expires_at,
    created_at
  ) VALUES (
    p_organization_id,
    p_project_id,
    p_principal_id,
    p_actor_principal_id,
    p_recent_session_id,
    p_operation,
    p_context_digest,
    p_issuer_idempotency_key,
    v_ticket_digest,
    v_receipt_digest,
    p_expires_at,
    v_now
  );

  RETURN jsonb_build_object(
    'ticket_id',v_ticket_digest,
    'step_up_receipt_id',v_receipt_digest,
    'context_digest',p_context_digest,
    'expires_at',p_expires_at
  );
END
$$;

CREATE OR REPLACE FUNCTION a1_cancel_scoped_identity_security_mutation_ticket(
  p_organization_id UUID,
  p_project_id UUID,
  p_principal_id UUID,
  p_actor_principal_id UUID,
  p_recent_session_id UUID,
  p_operation TEXT,
  p_issuer_idempotency_key TEXT,
  p_context_digest TEXT,
  p_ticket_digest TEXT,
  p_step_up_receipt_digest TEXT
) RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp
AS $$
DECLARE
  v_now CONSTANT TIMESTAMPTZ := clock_timestamp();
  v_issuance identity_security_ticket_issuance%ROWTYPE;
BEGIN
  IF current_setting('role', TRUE) <> 'a1_security_ticket_issuer'
     OR NOT pg_has_role(
       session_user,
       'a1_security_ticket_issuer',
       'MEMBER'
     ) THEN
    RAISE EXCEPTION 'identity_security_ticket_issuer_role_rejected'
      USING ERRCODE='42501';
  END IF;
  PERFORM a1_assert_role_nobypassrls('a1_security_ticket_issuer');
  PERFORM a1_assert_role_nobypassrls(session_user);

  IF p_principal_id IS NULL
     OR p_actor_principal_id IS DISTINCT FROM p_principal_id
     OR a1_current_principal_id() IS DISTINCT FROM p_principal_id
     OR p_recent_session_id IS NULL
     OR p_operation NOT IN (
       'password_enroll','password_change','password_recovery',
       'mfa_enroll','mfa_confirm','mfa_recovery_consume',
       'mfa_recovery_rotate','mfa_disable'
     )
     OR length(p_issuer_idempotency_key) NOT BETWEEN 8 AND 255
     OR p_issuer_idempotency_key !~ '^[A-Za-z0-9._:-]+$'
     OR NOT a1_identity_digest_valid(p_context_digest)
     OR NOT a1_identity_digest_valid(p_ticket_digest)
     OR NOT a1_identity_digest_valid(p_step_up_receipt_digest) THEN
    RAISE EXCEPTION 'identity_security_ticket_cancel_rejected'
      USING ERRCODE='42501';
  END IF;

  SELECT *
    INTO v_issuance
    FROM identity_security_ticket_issuance
   WHERE principal_id=p_principal_id
     AND operation=p_operation
     AND issuer_idempotency_key=p_issuer_idempotency_key
   FOR UPDATE;
  IF NOT FOUND
     OR v_issuance.organization_id IS DISTINCT FROM p_organization_id
     OR v_issuance.project_id IS DISTINCT FROM p_project_id
     OR v_issuance.actor_principal_id
          IS DISTINCT FROM p_actor_principal_id
     OR v_issuance.recent_session_id IS DISTINCT FROM p_recent_session_id
     OR v_issuance.context_digest IS DISTINCT FROM p_context_digest
     OR v_issuance.ticket_digest IS DISTINCT FROM p_ticket_digest
     OR v_issuance.step_up_receipt_digest
          IS DISTINCT FROM p_step_up_receipt_digest THEN
    RAISE EXCEPTION 'identity_security_ticket_cancel_rejected'
      USING ERRCODE='42501';
  END IF;

  UPDATE identity_security_ticket_issuance
     SET canceled_at=COALESCE(canceled_at,v_now)
   WHERE principal_id=p_principal_id
     AND operation=p_operation
     AND issuer_idempotency_key=p_issuer_idempotency_key;
  UPDATE identity_security_mutation_tickets
     SET consumed_at=COALESCE(consumed_at,v_now)
   WHERE ticket_digest=p_ticket_digest;
  UPDATE identity_security_receipts
     SET consumed_at=COALESCE(consumed_at,v_now)
   WHERE receipt_digest=p_step_up_receipt_digest;
  RETURN TRUE;
END
$$;

REVOKE ALL ON identity_account_security,
  identity_security_receipts,
  identity_security_mutation_tickets,
  identity_security_mutation_idempotency,
  identity_security_ticket_issuance
  FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_confirm_totp_enrollment(
  UUID,TEXT,TEXT,TEXT,INTEGER,TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_mutate_totp_recovery_lifecycle(
  UUID,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,INTEGER,TEXT,TEXT,UUID,TEXT,TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_issue_identity_security_mutation_ticket(
  TEXT,TEXT,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,INTEGER,TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_execute_identity_security_mutation(
  TEXT,TEXT,TEXT
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_resolve_identity_security_mutation_ticket(
  TEXT,TEXT,TEXT,TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_project_identity_security_processor_state(UUID)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_project_identity_security_mutation_replay(
  UUID,TEXT,TEXT
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_issue_scoped_identity_security_mutation_ticket(
  UUID,UUID,UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,INTEGER,TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_cancel_scoped_identity_security_mutation_ticket(
  UUID,UUID,UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT
) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='a1_runtime') THEN
    REVOKE CREATE ON SCHEMA public FROM a1_runtime;
    REVOKE ALL ON identity_account_security,
      identity_security_receipts,
      identity_security_mutation_tickets,
      identity_security_mutation_idempotency,
      identity_security_ticket_issuance
      FROM a1_runtime;
    REVOKE EXECUTE ON FUNCTION a1_confirm_totp_enrollment(
      UUID,TEXT,TEXT,TEXT,INTEGER,TIMESTAMPTZ
    ) FROM a1_runtime;
    REVOKE EXECUTE ON FUNCTION a1_mutate_totp_recovery_lifecycle(
      UUID,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,INTEGER,TEXT,TEXT,UUID,TEXT,TIMESTAMPTZ
    ) FROM a1_runtime;
    REVOKE EXECUTE ON FUNCTION a1_issue_identity_security_mutation_ticket(
      TEXT,TEXT,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,INTEGER,TIMESTAMPTZ
    ) FROM a1_runtime;
    REVOKE EXECUTE ON FUNCTION a1_execute_identity_security_mutation(
      TEXT,TEXT,TEXT
    ) FROM a1_runtime;
    REVOKE EXECUTE ON FUNCTION a1_resolve_identity_security_mutation_ticket(
      TEXT,TEXT,TEXT,TIMESTAMPTZ
    ) FROM a1_runtime;
    REVOKE EXECUTE ON FUNCTION a1_issue_scoped_identity_security_mutation_ticket(
      UUID,UUID,UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,INTEGER,TIMESTAMPTZ
    ) FROM a1_runtime;
    REVOKE EXECUTE ON FUNCTION a1_cancel_scoped_identity_security_mutation_ticket(
      UUID,UUID,UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT
    ) FROM a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_project_identity_security_processor_state(UUID)
      TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_project_identity_security_mutation_replay(
      UUID,TEXT,TEXT
    ) TO a1_runtime;
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname='a1_security_ticket_issuer'
  ) THEN
    REVOKE CREATE ON SCHEMA public FROM a1_security_ticket_issuer;
    REVOKE ALL ON identity_account_security,
      identity_security_receipts,
      identity_security_mutation_tickets,
      identity_security_mutation_idempotency,
      identity_security_ticket_issuance
      FROM a1_security_ticket_issuer;
    REVOKE EXECUTE ON FUNCTION a1_confirm_totp_enrollment(
      UUID,TEXT,TEXT,TEXT,INTEGER,TIMESTAMPTZ
    ) FROM a1_security_ticket_issuer;
    REVOKE EXECUTE ON FUNCTION a1_mutate_totp_recovery_lifecycle(
      UUID,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,INTEGER,TEXT,TEXT,UUID,TEXT,TIMESTAMPTZ
    ) FROM a1_security_ticket_issuer;
    REVOKE EXECUTE ON FUNCTION a1_issue_identity_security_mutation_ticket(
      TEXT,TEXT,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,INTEGER,TIMESTAMPTZ
    ) FROM a1_security_ticket_issuer;
    REVOKE EXECUTE ON FUNCTION a1_resolve_identity_security_mutation_ticket(
      TEXT,TEXT,TEXT,TIMESTAMPTZ
    ) FROM a1_security_ticket_issuer;
    REVOKE EXECUTE ON FUNCTION a1_resolve_identity_security_mutation_ticket(
      TEXT,TEXT,TEXT,UUID,TIMESTAMPTZ
    ) FROM a1_security_ticket_issuer;
    REVOKE EXECUTE ON FUNCTION a1_execute_identity_security_mutation(
      TEXT,TEXT,TEXT
    ) FROM a1_security_ticket_issuer;
    REVOKE EXECUTE ON FUNCTION a1_execute_identity_security_mutation(
      TEXT,TEXT,TEXT,UUID
    ) FROM a1_security_ticket_issuer;
    REVOKE EXECUTE ON FUNCTION a1_project_account_security(UUID)
      FROM a1_security_ticket_issuer;
    REVOKE EXECUTE ON FUNCTION a1_project_identity_security_processor_state(UUID)
      FROM a1_security_ticket_issuer;
    REVOKE EXECUTE ON FUNCTION a1_project_identity_security_mutation_replay(
      UUID,TEXT,TEXT
    ) FROM a1_security_ticket_issuer;
    GRANT EXECUTE ON FUNCTION a1_issue_scoped_identity_security_mutation_ticket(
      UUID,UUID,UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TEXT,INTEGER,TIMESTAMPTZ
    ) TO a1_security_ticket_issuer;
    GRANT EXECUTE ON FUNCTION a1_cancel_scoped_identity_security_mutation_ticket(
      UUID,UUID,UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT
    ) TO a1_security_ticket_issuer;
  END IF;
END
$$;

COMMIT;
