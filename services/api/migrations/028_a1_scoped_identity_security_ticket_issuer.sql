-- Give the password/MFA mutation-ticket issuer one narrowly scoped authority.
-- The issuer must be an independent NOSUPERUSER/NOBYPASSRLS/NOINHERIT
-- NOLOGIN role. A separate restricted LOGIN member must explicitly SET ROLE
-- before use. The issuer may create or cancel a ticket only for the canonical
-- principal and exact recent authenticated database session selected by the
-- caller.
BEGIN;

CREATE TABLE IF NOT EXISTS identity_security_ticket_issuance (
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  principal_id UUID NOT NULL,
  actor_principal_id UUID NOT NULL,
  recent_session_id UUID NOT NULL,
  operation TEXT NOT NULL CHECK (operation IN (
    'password_enroll','password_change','password_recovery',
    'mfa_enroll','mfa_confirm'
  )),
  context_digest TEXT NOT NULL CHECK (a1_identity_digest_valid(context_digest)),
  issuer_idempotency_key TEXT NOT NULL CHECK (
    length(issuer_idempotency_key) BETWEEN 8 AND 255
    AND issuer_idempotency_key ~ '^[A-Za-z0-9._:-]+$'
  ),
  ticket_digest TEXT NOT NULL
    REFERENCES identity_security_mutation_tickets(ticket_digest)
    ON DELETE RESTRICT,
  step_up_receipt_digest TEXT NOT NULL
    REFERENCES identity_security_receipts(receipt_digest)
    ON DELETE RESTRICT,
  expires_at TIMESTAMPTZ NOT NULL,
  canceled_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (principal_id, operation, issuer_idempotency_key),
  CONSTRAINT identity_security_ticket_issuance_project_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT identity_security_ticket_issuance_principal_fk
    FOREIGN KEY (principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT identity_security_ticket_issuance_actor_fk
    FOREIGN KEY (actor_principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT identity_security_ticket_issuance_session_fk
    FOREIGN KEY (recent_session_id)
    REFERENCES identity_sessions(id) ON DELETE RESTRICT,
  CONSTRAINT identity_security_ticket_issuance_ticket_key
    UNIQUE (ticket_digest),
  CONSTRAINT identity_security_ticket_issuance_receipt_key
    UNIQUE (step_up_receipt_digest),
  CONSTRAINT identity_security_ticket_issuance_actor_check
    CHECK (actor_principal_id = principal_id),
  CONSTRAINT identity_security_ticket_issuance_expiry_check
    CHECK (expires_at > created_at AND expires_at <= created_at + INTERVAL '5 minutes'),
  CONSTRAINT identity_security_ticket_issuance_cancel_check
    CHECK (canceled_at IS NULL OR canceled_at >= created_at)
);

CREATE INDEX IF NOT EXISTS identity_security_ticket_issuance_active_idx
  ON identity_security_ticket_issuance(
    principal_id, operation, expires_at
  )
  WHERE canceled_at IS NULL;

ALTER TABLE identity_security_ticket_issuance ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_security_ticket_issuance FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS identity_security_ticket_issuance_self
  ON identity_security_ticket_issuance;
CREATE POLICY identity_security_ticket_issuance_self
  ON identity_security_ticket_issuance
  USING (principal_id = a1_current_principal_id())
  WITH CHECK (principal_id = a1_current_principal_id());

CREATE OR REPLACE FUNCTION a1_issue_scoped_identity_security_mutation_ticket(
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
  p_recovery_batch_digest TEXT,
  p_recovery_code_count INTEGER,
  p_expires_at TIMESTAMPTZ
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  v_now CONSTANT TIMESTAMPTZ := clock_timestamp();
  v_expected_context_digest TEXT;
  v_recent_session_id UUID;
  v_existing identity_security_ticket_issuance%ROWTYPE;
  v_existing_ticket identity_security_mutation_tickets%ROWTYPE;
  v_ticket_digest TEXT;
  v_receipt_digest TEXT;
BEGIN
  IF current_setting('role', TRUE) <> 'a1_security_ticket_issuer'
     OR NOT pg_has_role(
       session_user,
       'a1_security_ticket_issuer',
       'MEMBER'
     ) THEN
    RAISE EXCEPTION 'identity_security_ticket_issuer_role_rejected'
      USING ERRCODE = '42501';
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
       'mfa_enroll','mfa_confirm'
     )
     OR length(p_issuer_idempotency_key) NOT BETWEEN 8 AND 255
     OR p_issuer_idempotency_key !~ '^[A-Za-z0-9._:-]+$'
     OR NOT a1_identity_digest_valid(p_context_digest)
     OR p_expires_at IS NULL
     OR p_expires_at <= v_now
     OR p_expires_at > v_now + INTERVAL '5 minutes' THEN
    RAISE EXCEPTION 'identity_security_ticket_scope_rejected'
      USING ERRCODE = '42501';
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
      USING ERRCODE = '42501';
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
      USING ERRCODE = '42501';
  END IF;
  IF p_operation = 'password_recovery'
     AND NOT EXISTS (
       SELECT 1
         FROM identity_sessions AS recent_session
         JOIN identity_credentials AS recovery_credential
           ON recovery_credential.principal_id =
                recent_session.principal_id
          AND recovery_credential.id = recent_session.credential_id
          AND recovery_credential.provider = 'email'
          AND recovery_credential.credential_kind IN (
                'email_otp',
                'email_password'
              )
          AND recovery_credential.status = 'active'
          AND recovery_credential.login_enabled
          AND recovery_credential.verified_at IS NOT NULL
        WHERE recent_session.id = p_recent_session_id
          AND recent_session.principal_id = p_principal_id
     ) THEN
    RAISE EXCEPTION 'identity_security_recovery_credential_rejected'
      USING ERRCODE = '42501';
  END IF;

  PERFORM 1
    FROM identity_principals
   WHERE id = p_principal_id
     AND status = 'active'
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity_security_ticket_principal_rejected'
      USING ERRCODE = '42501';
  END IF;

  SELECT *
    INTO v_existing
    FROM identity_security_ticket_issuance
   WHERE principal_id = p_principal_id
     AND operation = p_operation
     AND issuer_idempotency_key = p_issuer_idempotency_key
   FOR UPDATE;
  IF FOUND THEN
    SELECT *
      INTO v_existing_ticket
      FROM identity_security_mutation_tickets
     WHERE ticket_digest = v_existing.ticket_digest
     FOR UPDATE;
    IF NOT FOUND
       OR v_existing.organization_id IS DISTINCT FROM p_organization_id
       OR v_existing.project_id IS DISTINCT FROM p_project_id
       OR v_existing.actor_principal_id IS DISTINCT FROM p_actor_principal_id
       OR v_existing.recent_session_id IS DISTINCT FROM p_recent_session_id
       OR v_existing.context_digest IS DISTINCT FROM p_context_digest
       OR v_existing.canceled_at IS NOT NULL
       OR v_existing_ticket.secret_ref IS DISTINCT FROM p_secret_ref
       OR v_existing_ticket.secret_digest IS DISTINCT FROM p_secret_digest
       OR v_existing_ticket.recovery_batch_digest
            IS DISTINCT FROM p_recovery_batch_digest
       OR v_existing_ticket.recovery_code_count
            IS DISTINCT FROM p_recovery_code_count THEN
      RAISE EXCEPTION 'identity_security_ticket_idempotency_conflict'
        USING ERRCODE = '23505';
    END IF;
    RETURN jsonb_build_object(
      'ticket_id', v_existing.ticket_digest,
      'step_up_receipt_id', v_existing.step_up_receipt_digest,
      'context_digest', v_existing.context_digest,
      'expires_at', v_existing.expires_at
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
    p_recovery_batch_digest,
    p_recovery_code_count,
    p_expires_at
  ) THEN
    RAISE EXCEPTION 'identity_security_ticket_issuance_rejected'
      USING ERRCODE = '42501';
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
    'ticket_id', v_ticket_digest,
    'step_up_receipt_id', v_receipt_digest,
    'context_digest', p_context_digest,
    'expires_at', p_expires_at
  );
END;
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
SET search_path = pg_catalog, public, pg_temp
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
      USING ERRCODE = '42501';
  END IF;
  PERFORM a1_assert_role_nobypassrls('a1_security_ticket_issuer');
  PERFORM a1_assert_role_nobypassrls(session_user);

  IF p_principal_id IS NULL
     OR p_actor_principal_id IS DISTINCT FROM p_principal_id
     OR a1_current_principal_id() IS DISTINCT FROM p_principal_id
     OR p_recent_session_id IS NULL
     OR p_operation NOT IN (
       'password_enroll','password_change','password_recovery',
       'mfa_enroll','mfa_confirm'
     )
     OR length(p_issuer_idempotency_key) NOT BETWEEN 8 AND 255
     OR p_issuer_idempotency_key !~ '^[A-Za-z0-9._:-]+$'
     OR NOT a1_identity_digest_valid(p_context_digest)
     OR NOT a1_identity_digest_valid(p_ticket_digest)
     OR NOT a1_identity_digest_valid(p_step_up_receipt_digest) THEN
    RAISE EXCEPTION 'identity_security_ticket_cancel_rejected'
      USING ERRCODE = '42501';
  END IF;

  SELECT *
    INTO v_issuance
    FROM identity_security_ticket_issuance
   WHERE principal_id = p_principal_id
     AND operation = p_operation
     AND issuer_idempotency_key = p_issuer_idempotency_key
   FOR UPDATE;
  IF NOT FOUND
     OR v_issuance.organization_id IS DISTINCT FROM p_organization_id
     OR v_issuance.project_id IS DISTINCT FROM p_project_id
     OR v_issuance.actor_principal_id IS DISTINCT FROM p_actor_principal_id
     OR v_issuance.recent_session_id IS DISTINCT FROM p_recent_session_id
     OR v_issuance.context_digest IS DISTINCT FROM p_context_digest
     OR v_issuance.ticket_digest IS DISTINCT FROM p_ticket_digest
     OR v_issuance.step_up_receipt_digest
          IS DISTINCT FROM p_step_up_receipt_digest THEN
    RAISE EXCEPTION 'identity_security_ticket_cancel_rejected'
      USING ERRCODE = '42501';
  END IF;

  UPDATE identity_security_ticket_issuance
     SET canceled_at = COALESCE(canceled_at, v_now)
   WHERE principal_id = p_principal_id
     AND operation = p_operation
     AND issuer_idempotency_key = p_issuer_idempotency_key;
  UPDATE identity_security_mutation_tickets
     SET consumed_at = COALESCE(consumed_at, v_now)
   WHERE ticket_digest = p_ticket_digest;
  UPDATE identity_security_receipts
     SET consumed_at = COALESCE(consumed_at, v_now)
   WHERE receipt_digest = p_step_up_receipt_digest;
  RETURN TRUE;
END;
$$;

REVOKE ALL ON identity_security_ticket_issuance FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_issue_scoped_identity_security_mutation_ticket(
  UUID,UUID,UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_cancel_scoped_identity_security_mutation_ticket(
  UUID,UUID,UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT
) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a1_runtime') THEN
    REVOKE ALL ON identity_security_ticket_issuance FROM a1_runtime;
    REVOKE EXECUTE ON FUNCTION a1_issue_scoped_identity_security_mutation_ticket(
      UUID,UUID,UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TIMESTAMPTZ
    ) FROM a1_runtime;
    REVOKE EXECUTE ON FUNCTION a1_cancel_scoped_identity_security_mutation_ticket(
      UUID,UUID,UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT
    ) FROM a1_runtime;
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'a1_security_ticket_issuer'
  ) THEN
    REVOKE CREATE ON SCHEMA public FROM a1_security_ticket_issuer;
    REVOKE ALL ON identity_account_security,
      identity_security_receipts,
      identity_security_mutation_tickets,
      identity_security_mutation_idempotency,
      identity_security_ticket_issuance
      FROM a1_security_ticket_issuer;
    REVOKE EXECUTE ON FUNCTION a1_issue_identity_security_mutation_ticket(
      TEXT,TEXT,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TIMESTAMPTZ
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
    GRANT EXECUTE ON FUNCTION a1_issue_scoped_identity_security_mutation_ticket(
      UUID,UUID,UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TIMESTAMPTZ
    ) TO a1_security_ticket_issuer;
    GRANT EXECUTE ON FUNCTION a1_cancel_scoped_identity_security_mutation_ticket(
      UUID,UUID,UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT
    ) TO a1_security_ticket_issuer;
  END IF;
END;
$$;

COMMIT;
