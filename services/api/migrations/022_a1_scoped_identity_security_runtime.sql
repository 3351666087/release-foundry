-- Bind every runtime password/MFA projection, ticket resolution, and mutation
-- to the canonical principal selected by the authenticated HTTP session.
-- The original migration 018 functions remain private implementation
-- authorities; a1_runtime may execute only these scoped wrappers.
BEGIN;

CREATE OR REPLACE FUNCTION a1_resolve_identity_security_mutation_ticket(
  p_ticket_digest TEXT,
  p_step_up_receipt_digest TEXT,
  p_operation TEXT,
  p_principal_id UUID,
  p_now TIMESTAMPTZ
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

  v_projection := a1_resolve_identity_security_mutation_ticket(
    p_ticket_digest,
    p_step_up_receipt_digest,
    p_operation,
    p_now
  );
  IF NULLIF(v_projection->>'account_id','')::UUID IS DISTINCT FROM p_principal_id THEN
    RAISE EXCEPTION 'identity_security_ticket_scope_rejected'
      USING ERRCODE='42501';
  END IF;
  RETURN v_projection;
END
$$;

CREATE OR REPLACE FUNCTION a1_execute_identity_security_mutation(
  p_ticket_digest TEXT,
  p_idempotency_key TEXT,
  p_request_fingerprint TEXT,
  p_principal_id UUID
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path=pg_catalog,public,pg_temp
AS $$
DECLARE
  v_ticket_principal_id UUID;
BEGIN
  IF p_principal_id IS NULL
     OR a1_current_principal_id() IS DISTINCT FROM p_principal_id THEN
    RAISE EXCEPTION 'identity_security_principal_scope_rejected'
      USING ERRCODE='42501';
  END IF;

  SELECT principal_id
    INTO v_ticket_principal_id
    FROM identity_security_mutation_tickets
   WHERE ticket_digest=p_ticket_digest;
  IF NOT FOUND OR v_ticket_principal_id IS DISTINCT FROM p_principal_id THEN
    RAISE EXCEPTION 'identity_security_ticket_scope_rejected'
      USING ERRCODE='42501';
  END IF;

  RETURN a1_execute_identity_security_mutation(
    p_ticket_digest,
    p_idempotency_key,
    p_request_fingerprint
  );
END
$$;

CREATE OR REPLACE FUNCTION a1_project_account_security(
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
    'password_status',
      CASE WHEN security.password_secret_ref IS NULL THEN 'absent' ELSE 'set' END,
    'password_change_available',security.password_secret_ref IS NOT NULL,
    'password_recovery_available',EXISTS(
      SELECT 1
        FROM identity_account_emails email
       WHERE email.principal_id=p_principal_id
    ),
    'two_factor_status',security.two_factor_status,
    'two_factor_optional',TRUE,
    'two_factor_recommended',TRUE,
    'recovery_codes_remaining',security.recovery_codes_remaining,
    'security_version',security.security_version,
    'active_sessions',(
      SELECT count(*)
        FROM identity_sessions session
       WHERE session.principal_id=p_principal_id
         AND session.status='active'
    )
  )
    INTO v_projection
    FROM identity_account_security security
   WHERE security.principal_id=p_principal_id;
  RETURN v_projection;
END
$$;

REVOKE ALL ON FUNCTION a1_resolve_identity_security_mutation_ticket(
  TEXT,TEXT,TEXT,UUID,TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_execute_identity_security_mutation(
  TEXT,TEXT,TEXT,UUID
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_project_account_security(UUID) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='a1_runtime') THEN
    REVOKE EXECUTE ON FUNCTION a1_resolve_identity_security_mutation_ticket(
      TEXT,TEXT,TEXT,TIMESTAMPTZ
    ) FROM a1_runtime;
    REVOKE EXECUTE ON FUNCTION a1_execute_identity_security_mutation(
      TEXT,TEXT,TEXT
    ) FROM a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_resolve_identity_security_mutation_ticket(
      TEXT,TEXT,TEXT,UUID,TIMESTAMPTZ
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_execute_identity_security_mutation(
      TEXT,TEXT,TEXT,UUID
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_project_account_security(UUID) TO a1_runtime;
  END IF;
END
$$;

COMMIT;
