-- Canonical account security posture. Raw email, passwords, OTP seeds, and
-- provider subjects never enter these tables; callers supply keyed digests or
-- references to an external secret manager.
BEGIN;

CREATE TABLE IF NOT EXISTS identity_account_emails (
  principal_id UUID PRIMARY KEY REFERENCES identity_principals(id) ON DELETE RESTRICT,
  normalized_email_digest TEXT NOT NULL UNIQUE
    CHECK (a1_identity_digest_valid(normalized_email_digest)),
  source_provider TEXT NOT NULL CHECK (source_provider IN ('github', 'google', 'email')),
  verified_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS identity_account_security (
  principal_id UUID PRIMARY KEY REFERENCES identity_principals(id) ON DELETE RESTRICT,
  password_secret_ref TEXT,
  password_fingerprint_digest TEXT
    CHECK (password_fingerprint_digest IS NULL OR a1_identity_digest_valid(password_fingerprint_digest)),
  password_set_at TIMESTAMPTZ,
  two_factor_status TEXT NOT NULL DEFAULT 'disabled'
    CHECK (two_factor_status IN ('disabled', 'enabled')),
  two_factor_recommended BOOLEAN NOT NULL DEFAULT TRUE
    CHECK (two_factor_recommended),
  two_factor_enrolled_at TIMESTAMPTZ,
  security_version BIGINT NOT NULL DEFAULT 0 CHECK (security_version >= 0),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT identity_password_posture_check CHECK (
    (password_secret_ref IS NULL AND password_fingerprint_digest IS NULL AND password_set_at IS NULL)
    OR (password_secret_ref IS NOT NULL AND password_fingerprint_digest IS NOT NULL AND password_set_at IS NOT NULL)
  ),
  CONSTRAINT identity_two_factor_posture_check CHECK (
    (two_factor_status = 'enabled' AND two_factor_enrolled_at IS NOT NULL)
    OR (two_factor_status = 'disabled' AND two_factor_enrolled_at IS NULL)
  )
);

ALTER TABLE identity_account_emails ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_account_emails FORCE ROW LEVEL SECURITY;
ALTER TABLE identity_account_security ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_account_security FORCE ROW LEVEL SECURITY;

CREATE POLICY identity_account_emails_self ON identity_account_emails
  USING (principal_id = a1_current_principal_id())
  WITH CHECK (principal_id = a1_current_principal_id());
CREATE POLICY identity_account_security_self ON identity_account_security
  USING (principal_id = a1_current_principal_id())
  WITH CHECK (principal_id = a1_current_principal_id());

CREATE OR REPLACE FUNCTION a1_sync_verified_oauth_email(
  p_principal_id UUID,
  p_provider TEXT,
  p_email_digest TEXT,
  p_actor_principal_id UUID,
  p_step_up_at TIMESTAMPTZ,
  p_csrf_validated BOOLEAN
) RETURNS TEXT
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE existing_owner UUID;
BEGIN
  IF p_principal_id IS NULL OR p_actor_principal_id <> p_principal_id
     OR p_provider NOT IN ('github', 'google')
     OR NOT a1_identity_digest_valid(p_email_digest)
     OR NOT p_csrf_validated OR p_step_up_at < clock_timestamp() - INTERVAL '10 minutes' THEN
    RAISE EXCEPTION 'verified email sync rejected' USING ERRCODE = '42501';
  END IF;
  SELECT principal_id INTO existing_owner FROM identity_account_emails
   WHERE normalized_email_digest = p_email_digest FOR UPDATE;
  IF existing_owner IS NOT NULL AND existing_owner <> p_principal_id THEN
    PERFORM a1_identity_write_event(
      p_principal_id, NULL, NULL, p_actor_principal_id,
      'identity.canonical_email.conflict', 'principal', p_principal_id, NULL,
      jsonb_build_object('provider', p_provider, 'outcome', 'rejected')
    );
    RAISE EXCEPTION 'canonical_email_conflict' USING ERRCODE = '23505';
  END IF;
  INSERT INTO identity_account_emails(principal_id, normalized_email_digest, source_provider, verified_at)
    VALUES (p_principal_id, p_email_digest, p_provider, clock_timestamp())
  ON CONFLICT (principal_id) DO UPDATE SET
    normalized_email_digest = EXCLUDED.normalized_email_digest,
    source_provider = EXCLUDED.source_provider,
    verified_at = EXCLUDED.verified_at,
    updated_at = clock_timestamp()
  WHERE identity_account_emails.normalized_email_digest = EXCLUDED.normalized_email_digest;
  INSERT INTO identity_account_security(principal_id) VALUES (p_principal_id)
    ON CONFLICT (principal_id) DO NOTHING;
  PERFORM a1_identity_write_event(
    p_principal_id, NULL, NULL, p_actor_principal_id,
    'identity.canonical_email.synced', 'principal', p_principal_id, NULL,
    jsonb_build_object('provider', p_provider, 'verified', true, 'outcome', 'success')
  );
  RETURN 'synced';
END $$;

CREATE OR REPLACE FUNCTION a1_set_account_password(
  p_principal_id UUID,
  p_secret_ref TEXT,
  p_fingerprint_digest TEXT,
  p_actor_principal_id UUID,
  p_step_up_at TIMESTAMPTZ,
  p_csrf_validated BOOLEAN
) RETURNS BIGINT
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE next_version BIGINT;
BEGIN
  IF p_principal_id IS NULL OR p_actor_principal_id <> p_principal_id
     OR p_secret_ref IS NULL OR length(p_secret_ref) < 16
     OR NOT a1_identity_digest_valid(p_fingerprint_digest)
     OR NOT p_csrf_validated OR p_step_up_at < clock_timestamp() - INTERVAL '10 minutes' THEN
    RAISE EXCEPTION 'password enrollment rejected' USING ERRCODE = '42501';
  END IF;
  INSERT INTO identity_account_security(
    principal_id, password_secret_ref, password_fingerprint_digest, password_set_at, security_version
  ) VALUES (
    p_principal_id, p_secret_ref, p_fingerprint_digest, clock_timestamp(), 1
  ) ON CONFLICT (principal_id) DO UPDATE SET
    password_secret_ref = EXCLUDED.password_secret_ref,
    password_fingerprint_digest = EXCLUDED.password_fingerprint_digest,
    password_set_at = clock_timestamp(),
    security_version = identity_account_security.security_version + 1,
    updated_at = clock_timestamp()
  RETURNING security_version INTO next_version;
  UPDATE identity_sessions SET status = 'revoked', revoked_at = clock_timestamp(),
    revoke_reason_code = 'password_changed'
    WHERE principal_id = p_principal_id AND status = 'active';
  PERFORM a1_identity_write_event(
    p_principal_id, NULL, NULL, p_actor_principal_id,
    'identity.password.changed', 'principal', p_principal_id, NULL,
    jsonb_build_object(
      'sessions_revoked', true,
      'security_version', next_version,
      'outcome', 'success'
    )
  );
  RETURN next_version;
END $$;

CREATE OR REPLACE FUNCTION a1_set_account_two_factor(
  p_principal_id UUID,
  p_enabled BOOLEAN,
  p_actor_principal_id UUID,
  p_step_up_at TIMESTAMPTZ,
  p_csrf_validated BOOLEAN
) RETURNS TEXT
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
  IF p_principal_id IS NULL OR p_actor_principal_id <> p_principal_id
     OR NOT p_csrf_validated OR p_step_up_at < clock_timestamp() - INTERVAL '10 minutes' THEN
    RAISE EXCEPTION 'two factor change rejected' USING ERRCODE = '42501';
  END IF;
  INSERT INTO identity_account_security(principal_id, two_factor_status, two_factor_enrolled_at, security_version)
    VALUES (p_principal_id, CASE WHEN p_enabled THEN 'enabled' ELSE 'disabled' END,
            CASE WHEN p_enabled THEN clock_timestamp() ELSE NULL END, 1)
  ON CONFLICT (principal_id) DO UPDATE SET
    two_factor_status = EXCLUDED.two_factor_status,
    two_factor_enrolled_at = EXCLUDED.two_factor_enrolled_at,
    security_version = identity_account_security.security_version + 1,
    updated_at = clock_timestamp();
  UPDATE identity_sessions SET status = 'revoked', revoked_at = clock_timestamp(),
    revoke_reason_code = 'two_factor_changed'
    WHERE principal_id = p_principal_id AND status = 'active';
  PERFORM a1_identity_write_event(
    p_principal_id, NULL, NULL, p_actor_principal_id,
    'identity.two_factor.changed', 'principal', p_principal_id, NULL,
    jsonb_build_object(
      'enabled', p_enabled,
      'recommended', true,
      'sessions_revoked', true,
      'outcome', 'success'
    )
  );
  RETURN CASE WHEN p_enabled THEN 'enabled' ELSE 'disabled' END;
END $$;

REVOKE ALL ON identity_account_emails, identity_account_security FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_sync_verified_oauth_email(UUID,TEXT,TEXT,UUID,TIMESTAMPTZ,BOOLEAN) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_set_account_password(UUID,TEXT,TEXT,UUID,TIMESTAMPTZ,BOOLEAN) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_set_account_two_factor(UUID,BOOLEAN,UUID,TIMESTAMPTZ,BOOLEAN) FROM PUBLIC;

COMMIT;
