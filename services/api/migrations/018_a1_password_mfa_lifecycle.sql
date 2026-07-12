-- Authoritative password and MFA lifecycle. Secret values never enter public
-- projections: the runtime supplies vault references and keyed digests only.
BEGIN;

ALTER TABLE identity_account_security
  ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS password_recovery_version BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS totp_secret_ref TEXT,
  ADD COLUMN IF NOT EXISTS totp_secret_digest TEXT,
  ADD COLUMN IF NOT EXISTS totp_pending_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS recovery_code_batch_digest TEXT,
  ADD COLUMN IF NOT EXISTS recovery_codes_remaining INTEGER NOT NULL DEFAULT 0;

-- Drop the v016 constraints before introducing the pending enrollment state.
ALTER TABLE identity_account_security DROP CONSTRAINT IF EXISTS identity_two_factor_posture_check;
ALTER TABLE identity_account_security DROP CONSTRAINT IF EXISTS identity_account_security_two_factor_status_check;
ALTER TABLE identity_account_security ADD CONSTRAINT identity_totp_posture_check CHECK (
  (two_factor_status = 'disabled' AND totp_secret_ref IS NULL AND
   totp_secret_digest IS NULL AND two_factor_enrolled_at IS NULL)
  OR (two_factor_status = 'pending' AND totp_secret_ref IS NOT NULL AND
      totp_secret_digest IS NOT NULL AND totp_pending_at IS NOT NULL)
  OR (two_factor_status = 'enabled' AND totp_secret_ref IS NOT NULL AND
      totp_secret_digest IS NOT NULL AND two_factor_enrolled_at IS NOT NULL)
);
ALTER TABLE identity_account_security ADD CONSTRAINT identity_account_security_two_factor_status_check
  CHECK (two_factor_status IN ('disabled','pending','enabled'));
ALTER TABLE identity_account_security ADD CONSTRAINT identity_recovery_code_count_check
  CHECK (recovery_codes_remaining BETWEEN 0 AND 64);

CREATE TABLE IF NOT EXISTS identity_security_receipts (
  receipt_digest TEXT PRIMARY KEY CHECK (a1_identity_digest_valid(receipt_digest)),
  principal_id UUID NOT NULL REFERENCES identity_principals(id) ON DELETE CASCADE,
  purpose TEXT NOT NULL CHECK (purpose IN
    ('password_enroll','password_change','password_recovery','mfa_enroll','mfa_confirm','mfa_disable','mfa_recovery')),
  context_digest TEXT NOT NULL CHECK (a1_identity_digest_valid(context_digest)),
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS identity_security_receipts_active_idx
  ON identity_security_receipts(principal_id,purpose,expires_at) WHERE consumed_at IS NULL;
ALTER TABLE identity_security_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_security_receipts FORCE ROW LEVEL SECURITY;
CREATE POLICY identity_security_receipts_self ON identity_security_receipts
  USING (principal_id=a1_current_principal_id()) WITH CHECK (principal_id=a1_current_principal_id());

CREATE OR REPLACE FUNCTION a1_consume_identity_security_receipt(
  p_receipt_digest TEXT, p_principal_id UUID, p_purpose TEXT,
  p_context_digest TEXT, p_now TIMESTAMPTZ
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
  UPDATE identity_security_receipts SET consumed_at=p_now
   WHERE receipt_digest=p_receipt_digest AND principal_id=p_principal_id
     AND purpose=p_purpose AND context_digest=p_context_digest
     AND consumed_at IS NULL AND expires_at>p_now;
  RETURN FOUND;
END $$;

-- v016 exposed a boolean MFA switch before TOTP proof existed. Preserve the
-- signature for deployed callers, but fail closed so MFA can only be enabled
-- through begin/confirm below and cannot bypass possession verification.
CREATE OR REPLACE FUNCTION a1_set_account_two_factor(
  p_principal_id UUID, p_enabled BOOLEAN, p_actor_principal_id UUID,
  p_step_up_at TIMESTAMPTZ, p_csrf_validated BOOLEAN
) RETURNS TEXT
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
  RAISE EXCEPTION 'two_factor_legacy_mutation_disabled' USING ERRCODE='0A000';
END $$;

CREATE OR REPLACE FUNCTION a1_mutate_account_password(
  p_principal_id UUID, p_operation TEXT, p_secret_ref TEXT,
  p_fingerprint_digest TEXT, p_receipt_digest TEXT,
  p_context_digest TEXT, p_actor_principal_id UUID, p_now TIMESTAMPTZ
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE v_security identity_account_security%ROWTYPE; v_revoked BIGINT; v_version BIGINT;
BEGIN
  IF p_operation NOT IN ('password_enroll','password_change','password_recovery')
     OR p_actor_principal_id<>p_principal_id OR length(p_secret_ref)<16
     OR NOT a1_identity_digest_valid(p_fingerprint_digest) THEN
    RAISE EXCEPTION 'password mutation rejected' USING ERRCODE='42501';
  END IF;
  SELECT * INTO v_security FROM identity_account_security
   WHERE principal_id=p_principal_id FOR UPDATE;
  IF p_operation='password_enroll' AND v_security.password_secret_ref IS NOT NULL THEN
    RAISE EXCEPTION 'password_already_enrolled' USING ERRCODE='23505';
  ELSIF p_operation='password_change' AND v_security.password_secret_ref IS NULL THEN
    RAISE EXCEPTION 'password_not_enrolled' USING ERRCODE='23514';
  END IF;
  IF NOT a1_consume_identity_security_receipt(p_receipt_digest,p_principal_id,
       p_operation,p_context_digest,p_now) THEN
    RAISE EXCEPTION 'security_receipt_unavailable' USING ERRCODE='42501';
  END IF;
  INSERT INTO identity_account_security(principal_id,password_secret_ref,
    password_fingerprint_digest,password_set_at,password_changed_at,security_version)
  VALUES(p_principal_id,p_secret_ref,p_fingerprint_digest,p_now,p_now,1)
  ON CONFLICT(principal_id) DO UPDATE SET password_secret_ref=EXCLUDED.password_secret_ref,
    password_fingerprint_digest=EXCLUDED.password_fingerprint_digest,
    password_set_at=COALESCE(identity_account_security.password_set_at,p_now),
    password_changed_at=p_now, security_version=identity_account_security.security_version+1,
    password_recovery_version=identity_account_security.password_recovery_version+
      CASE WHEN p_operation='password_recovery' THEN 1 ELSE 0 END, updated_at=p_now
  RETURNING security_version INTO v_version;
  UPDATE identity_sessions SET status='revoked',revoked_at=p_now,
    revoke_reason_code=p_operation WHERE principal_id=p_principal_id AND status='active';
  GET DIAGNOSTICS v_revoked=ROW_COUNT;
  PERFORM a1_identity_write_event(p_principal_id,NULL,NULL,p_actor_principal_id,
    'identity.'||p_operation,'principal',p_principal_id,NULL,
    jsonb_build_object('security_version',v_version,'sessions_revoked',v_revoked,'outcome','success'));
  RETURN jsonb_build_object('password_status','set','security_version',v_version,
    'sessions_revoked',v_revoked,'reauthentication_required',TRUE);
END $$;

CREATE OR REPLACE FUNCTION a1_begin_totp_enrollment(
  p_principal_id UUID,p_secret_ref TEXT,p_secret_digest TEXT,
  p_receipt_digest TEXT,p_context_digest TEXT,p_actor_principal_id UUID,p_now TIMESTAMPTZ
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
  IF p_actor_principal_id<>p_principal_id OR length(p_secret_ref)<16
     OR NOT a1_identity_digest_valid(p_secret_digest)
     OR NOT a1_consume_identity_security_receipt(p_receipt_digest,p_principal_id,
          'mfa_enroll',p_context_digest,p_now) THEN
    RAISE EXCEPTION 'mfa enrollment rejected' USING ERRCODE='42501';
  END IF;
  INSERT INTO identity_account_security(principal_id,two_factor_status,totp_secret_ref,
    totp_secret_digest,totp_pending_at,security_version)
  VALUES(p_principal_id,'pending',p_secret_ref,p_secret_digest,p_now,1)
  ON CONFLICT(principal_id) DO UPDATE SET two_factor_status='pending',
    totp_secret_ref=p_secret_ref,totp_secret_digest=p_secret_digest,totp_pending_at=p_now,
    two_factor_enrolled_at=NULL,recovery_code_batch_digest=NULL,recovery_codes_remaining=0,
    security_version=identity_account_security.security_version+1,updated_at=p_now;
  RETURN jsonb_build_object('two_factor_status','pending','confirmation_required',TRUE);
END $$;

CREATE OR REPLACE FUNCTION a1_confirm_totp_enrollment(
  p_principal_id UUID,p_receipt_digest TEXT,p_context_digest TEXT,
  p_recovery_batch_digest TEXT,p_recovery_code_count INTEGER,p_now TIMESTAMPTZ
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE v_revoked BIGINT;
BEGIN
  IF p_recovery_code_count NOT BETWEEN 6 AND 20
     OR NOT a1_identity_digest_valid(p_recovery_batch_digest)
     OR NOT a1_consume_identity_security_receipt(p_receipt_digest,p_principal_id,
          'mfa_confirm',p_context_digest,p_now) THEN
    RAISE EXCEPTION 'mfa confirmation rejected' USING ERRCODE='42501';
  END IF;
  UPDATE identity_account_security SET two_factor_status='enabled',
    two_factor_enrolled_at=p_now,recovery_code_batch_digest=p_recovery_batch_digest,
    recovery_codes_remaining=p_recovery_code_count,security_version=security_version+1,updated_at=p_now
   WHERE principal_id=p_principal_id AND two_factor_status='pending'
     AND totp_pending_at>p_now-INTERVAL '15 minutes';
  IF NOT FOUND THEN RAISE EXCEPTION 'mfa_enrollment_unavailable' USING ERRCODE='55000'; END IF;
  UPDATE identity_sessions SET status='revoked',revoked_at=p_now,revoke_reason_code='mfa_enabled'
   WHERE principal_id=p_principal_id AND status='active';
  GET DIAGNOSTICS v_revoked=ROW_COUNT;
  RETURN jsonb_build_object('two_factor_status','enabled','recovery_codes_remaining',
    p_recovery_code_count,'sessions_revoked',v_revoked,'reauthentication_required',TRUE);
END $$;

CREATE OR REPLACE FUNCTION a1_project_account_security(p_principal_id UUID) RETURNS JSONB
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT jsonb_build_object('password_status',CASE WHEN password_secret_ref IS NULL THEN 'absent' ELSE 'set' END,
   'password_change_available',password_secret_ref IS NOT NULL,
   'password_recovery_available',EXISTS(SELECT 1 FROM identity_account_emails e WHERE e.principal_id=p_principal_id),
   'two_factor_status',two_factor_status,'two_factor_optional',TRUE,'two_factor_recommended',TRUE,
   'recovery_codes_remaining',recovery_codes_remaining,'security_version',security_version,
   'active_sessions',(SELECT count(*) FROM identity_sessions s WHERE s.principal_id=p_principal_id AND s.status='active'))
 FROM identity_account_security WHERE principal_id=p_principal_id
$$;

REVOKE ALL ON identity_security_receipts FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_consume_identity_security_receipt(TEXT,UUID,TEXT,TEXT,TIMESTAMPTZ) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_mutate_account_password(UUID,TEXT,TEXT,TEXT,TEXT,TEXT,UUID,TIMESTAMPTZ) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_begin_totp_enrollment(UUID,TEXT,TEXT,TEXT,TEXT,UUID,TIMESTAMPTZ) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_confirm_totp_enrollment(UUID,TEXT,TEXT,TEXT,INTEGER,TIMESTAMPTZ) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_project_account_security(UUID) FROM PUBLIC;

COMMIT;
