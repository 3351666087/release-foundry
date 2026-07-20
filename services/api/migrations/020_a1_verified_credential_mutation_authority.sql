-- Existing-account credential binding is an account-security mutation, not a
-- public registration primitive.  Extend the trusted mutation-ticket
-- authority and require a recent authenticated session, an exact step-up
-- receipt, and an exact request-bound ticket before migration 012 may link a
-- new verified credential.
BEGIN;

ALTER TABLE identity_security_receipts
  DROP CONSTRAINT IF EXISTS identity_security_receipts_purpose_check;
ALTER TABLE identity_security_receipts
  ADD CONSTRAINT identity_security_receipts_purpose_check CHECK (purpose IN (
    'password_enroll','password_change','password_recovery',
    'mfa_enroll','mfa_confirm','mfa_disable','mfa_recovery',
    'credential_bind'
  ));

ALTER TABLE identity_security_mutation_tickets
  DROP CONSTRAINT IF EXISTS identity_security_mutation_tickets_operation_check;
ALTER TABLE identity_security_mutation_tickets
  DROP CONSTRAINT IF EXISTS identity_security_mutation_ticket_payload_check;
ALTER TABLE identity_security_mutation_tickets
  ADD CONSTRAINT identity_security_mutation_tickets_operation_check CHECK (
    operation IN (
      'password_enroll','password_change','password_recovery',
      'mfa_enroll','mfa_confirm','credential_bind'
    )
  );
ALTER TABLE identity_security_mutation_tickets
  ADD CONSTRAINT identity_security_mutation_ticket_payload_check CHECK (
    (operation IN ('password_enroll','password_change','password_recovery')
      AND secret_ref IS NOT NULL AND secret_digest IS NOT NULL
      AND length(secret_ref)>=16 AND a1_identity_digest_valid(secret_digest)
      AND recovery_batch_digest IS NULL AND recovery_code_count IS NULL)
    OR
    (operation='mfa_enroll'
      AND secret_ref IS NOT NULL AND secret_digest IS NOT NULL
      AND length(secret_ref)>=16 AND a1_identity_digest_valid(secret_digest)
      AND recovery_batch_digest IS NULL AND recovery_code_count IS NULL)
    OR
    (operation='mfa_confirm'
      AND secret_ref IS NULL AND secret_digest IS NULL
      AND recovery_batch_digest IS NOT NULL
      AND a1_identity_digest_valid(recovery_batch_digest)
      AND recovery_code_count BETWEEN 6 AND 20)
    OR
    (operation='credential_bind'
      AND secret_ref IS NULL AND secret_digest IS NULL
      AND recovery_batch_digest IS NULL AND recovery_code_count IS NULL)
  );

CREATE OR REPLACE FUNCTION a1_issue_identity_security_mutation_ticket(
  p_ticket_digest TEXT,p_step_up_receipt_digest TEXT,p_principal_id UUID,
  p_actor_principal_id UUID,p_operation TEXT,p_context_digest TEXT,
  p_secret_ref TEXT,p_secret_digest TEXT,p_recovery_batch_digest TEXT,
  p_recovery_code_count INTEGER,p_expires_at TIMESTAMPTZ
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
  v_receipt identity_security_receipts%ROWTYPE;
  v_existing identity_security_mutation_tickets%ROWTYPE;
  v_now CONSTANT TIMESTAMPTZ := clock_timestamp();
BEGIN
  IF NOT a1_identity_digest_valid(p_ticket_digest)
     OR p_actor_principal_id<>p_principal_id
     OR p_operation NOT IN (
       'password_enroll','password_change','password_recovery',
       'mfa_enroll','mfa_confirm','credential_bind'
     ) THEN
    RAISE EXCEPTION 'identity_security_ticket_rejected' USING ERRCODE='42501';
  END IF;

  SELECT * INTO v_existing FROM identity_security_mutation_tickets
   WHERE ticket_digest=p_ticket_digest FOR UPDATE;
  IF FOUND THEN
    IF v_existing.step_up_receipt_digest IS NOT DISTINCT FROM p_step_up_receipt_digest
       AND v_existing.principal_id IS NOT DISTINCT FROM p_principal_id
       AND v_existing.actor_principal_id IS NOT DISTINCT FROM p_actor_principal_id
       AND v_existing.operation IS NOT DISTINCT FROM p_operation
       AND v_existing.context_digest IS NOT DISTINCT FROM p_context_digest
       AND v_existing.secret_ref IS NOT DISTINCT FROM p_secret_ref
       AND v_existing.secret_digest IS NOT DISTINCT FROM p_secret_digest
       AND v_existing.recovery_batch_digest IS NOT DISTINCT FROM p_recovery_batch_digest
       AND v_existing.recovery_code_count IS NOT DISTINCT FROM p_recovery_code_count
       AND v_existing.expires_at IS NOT DISTINCT FROM p_expires_at THEN
      RETURN TRUE;
    END IF;
    RAISE EXCEPTION 'identity_security_ticket_issuance_conflict' USING ERRCODE='23505';
  END IF;

  IF p_expires_at IS NULL OR p_expires_at<=v_now THEN
    RAISE EXCEPTION 'identity_security_ticket_rejected' USING ERRCODE='42501';
  END IF;

  SELECT * INTO v_receipt FROM identity_security_receipts
   WHERE receipt_digest=p_step_up_receipt_digest
     AND principal_id=p_principal_id AND purpose=p_operation
     AND context_digest=p_context_digest
     AND consumed_at IS NULL AND expires_at>v_now
   FOR UPDATE;
  IF NOT FOUND OR p_expires_at>v_receipt.expires_at THEN
    RAISE EXCEPTION 'identity_security_ticket_receipt_rejected' USING ERRCODE='42501';
  END IF;

  SELECT * INTO v_existing FROM identity_security_mutation_tickets
   WHERE ticket_digest=p_ticket_digest FOR UPDATE;
  IF FOUND THEN
    IF v_existing.step_up_receipt_digest IS NOT DISTINCT FROM p_step_up_receipt_digest
       AND v_existing.principal_id IS NOT DISTINCT FROM p_principal_id
       AND v_existing.actor_principal_id IS NOT DISTINCT FROM p_actor_principal_id
       AND v_existing.operation IS NOT DISTINCT FROM p_operation
       AND v_existing.context_digest IS NOT DISTINCT FROM p_context_digest
       AND v_existing.secret_ref IS NOT DISTINCT FROM p_secret_ref
       AND v_existing.secret_digest IS NOT DISTINCT FROM p_secret_digest
       AND v_existing.recovery_batch_digest IS NOT DISTINCT FROM p_recovery_batch_digest
       AND v_existing.recovery_code_count IS NOT DISTINCT FROM p_recovery_code_count
       AND v_existing.expires_at IS NOT DISTINCT FROM p_expires_at THEN
      RETURN TRUE;
    END IF;
    RAISE EXCEPTION 'identity_security_ticket_issuance_conflict' USING ERRCODE='23505';
  END IF;

  PERFORM 1 FROM identity_security_mutation_tickets
   WHERE step_up_receipt_digest=p_step_up_receipt_digest FOR UPDATE;
  IF FOUND THEN
    RAISE EXCEPTION 'identity_security_receipt_ticket_conflict' USING ERRCODE='23505';
  END IF;

  INSERT INTO identity_security_mutation_tickets(
    ticket_digest,step_up_receipt_digest,principal_id,actor_principal_id,
    operation,context_digest,secret_ref,secret_digest,recovery_batch_digest,
    recovery_code_count,expires_at,created_at
  ) VALUES (
    p_ticket_digest,p_step_up_receipt_digest,p_principal_id,p_actor_principal_id,
    p_operation,p_context_digest,p_secret_ref,p_secret_digest,p_recovery_batch_digest,
    p_recovery_code_count,p_expires_at,v_now
  );
  RETURN TRUE;
END $$;

CREATE OR REPLACE FUNCTION a1_resolve_identity_security_mutation_ticket(
  p_ticket_digest TEXT,p_step_up_receipt_digest TEXT,p_operation TEXT,
  p_now TIMESTAMPTZ
) RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE v_ticket identity_security_mutation_tickets%ROWTYPE;
BEGIN
  IF NOT a1_identity_digest_valid(p_ticket_digest)
     OR NOT a1_identity_digest_valid(p_step_up_receipt_digest)
     OR p_operation NOT IN (
       'password_enroll','password_change','password_recovery',
       'mfa_enroll','mfa_confirm','credential_bind'
     ) THEN
    RAISE EXCEPTION 'identity_security_ticket_rejected' USING ERRCODE='42501';
  END IF;

  SELECT * INTO v_ticket FROM identity_security_mutation_tickets
   WHERE ticket_digest=p_ticket_digest
     AND step_up_receipt_digest=p_step_up_receipt_digest
     AND operation=p_operation;
  IF NOT FOUND OR v_ticket.expires_at<=p_now
     OR (v_ticket.consumed_at IS NOT NULL AND p_operation<>'credential_bind') THEN
    RAISE EXCEPTION 'identity_security_ticket_unavailable' USING ERRCODE='42501';
  END IF;

  RETURN jsonb_build_object(
    'ticket_id',v_ticket.ticket_digest,
    'account_id',v_ticket.principal_id,
    'operation',v_ticket.operation,
    'step_up_receipt_id',v_ticket.step_up_receipt_digest,
    'expires_at',v_ticket.expires_at
  );
END $$;

CREATE OR REPLACE FUNCTION a1_bind_verified_identity_credential_authorized(
  p_organization_id UUID,
  p_project_id UUID,
  p_receipt_digest TEXT,
  p_principal_id UUID,
  p_session_digest TEXT,
  p_mutation_ticket_digest TEXT,
  p_step_up_receipt_digest TEXT,
  p_idempotency_digest TEXT,
  p_request_digest TEXT,
  p_event_digest TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp
AS $$
DECLARE
  v_ticket identity_security_mutation_tickets%ROWTYPE;
  v_now CONSTANT TIMESTAMPTZ := clock_timestamp();
  v_result UUID;
BEGIN
  PERFORM a1_identity_session_assert_scope(
    p_organization_id,p_project_id,p_principal_id
  );
  IF NOT a1_identity_digest_valid(p_receipt_digest)
     OR NOT a1_identity_digest_valid(p_session_digest)
     OR NOT a1_identity_digest_valid(p_mutation_ticket_digest)
     OR NOT a1_identity_digest_valid(p_step_up_receipt_digest)
     OR NOT a1_identity_digest_valid(p_idempotency_digest)
     OR NOT a1_identity_digest_valid(p_request_digest)
     OR NOT a1_identity_digest_valid(p_event_digest)
     OR NOT a1_identity_public_metadata(p_metadata) THEN
    RAISE EXCEPTION 'verified_credential_binding_authorization_invalid'
      USING ERRCODE='22023';
  END IF;

  SELECT * INTO v_ticket
    FROM identity_security_mutation_tickets
   WHERE ticket_digest=p_mutation_ticket_digest
   FOR UPDATE;
  IF NOT FOUND
     OR v_ticket.operation<>'credential_bind'
     OR v_ticket.principal_id<>p_principal_id
     OR v_ticket.actor_principal_id<>p_principal_id
     OR v_ticket.step_up_receipt_digest<>p_step_up_receipt_digest
     OR v_ticket.context_digest<>p_request_digest
     OR v_ticket.secret_ref IS NOT NULL
     OR v_ticket.secret_digest IS NOT NULL
     OR v_ticket.recovery_batch_digest IS NOT NULL
     OR v_ticket.recovery_code_count IS NOT NULL THEN
    RAISE EXCEPTION 'verified_credential_binding_authorization_rejected'
      USING ERRCODE='42501';
  END IF;

  IF v_ticket.consumed_at IS NOT NULL THEN
    RETURN a1_bind_verified_identity_credential(
      p_organization_id,p_project_id,p_receipt_digest,p_principal_id,
      p_idempotency_digest,p_request_digest,p_event_digest,p_metadata
    );
  END IF;
  IF v_ticket.expires_at<=v_now THEN
    RAISE EXCEPTION 'verified_credential_binding_authorization_expired'
      USING ERRCODE='42501';
  END IF;

  PERFORM a1_assert_recent_identity_authentication(
    p_organization_id,p_project_id,p_principal_id,p_session_digest,600,'aal1'
  );
  IF NOT a1_consume_identity_security_receipt(
    p_step_up_receipt_digest,p_principal_id,'credential_bind',
    p_request_digest,v_now
  ) THEN
    RAISE EXCEPTION 'verified_credential_binding_step_up_unavailable'
      USING ERRCODE='42501';
  END IF;

  UPDATE identity_security_mutation_tickets
     SET consumed_at=v_now
   WHERE ticket_digest=p_mutation_ticket_digest
     AND consumed_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'verified_credential_binding_ticket_unavailable'
      USING ERRCODE='42501';
  END IF;

  v_result := a1_bind_verified_identity_credential(
    p_organization_id,p_project_id,p_receipt_digest,p_principal_id,
    p_idempotency_digest,p_request_digest,p_event_digest,p_metadata
  );
  RETURN v_result;
END;
$$;

REVOKE ALL ON FUNCTION a1_bind_verified_identity_credential_authorized(
  UUID,UUID,TEXT,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_bind_verified_identity_credential(
  UUID,UUID,TEXT,UUID,TEXT,TEXT,TEXT,JSONB
) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='a1_runtime') THEN
    REVOKE EXECUTE ON FUNCTION a1_bind_verified_identity_credential(
      UUID,UUID,TEXT,UUID,TEXT,TEXT,TEXT,JSONB
    ) FROM a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_bind_verified_identity_credential_authorized(
      UUID,UUID,TEXT,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,JSONB
    ) TO a1_runtime;
  END IF;
END
$$;

COMMIT;
