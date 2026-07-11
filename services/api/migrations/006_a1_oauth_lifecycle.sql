-- A1 Postgres OAuth account lifecycle.
-- Sensitive OAuth material is represented only by irreversible digests or
-- references to an external secret manager.

BEGIN;

CREATE OR REPLACE FUNCTION a1_oauth_digest(p_value TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
  SELECT encode(digest(p_value, 'sha256'), 'hex');
$$;

CREATE OR REPLACE FUNCTION a1_oauth_reference_only(p_reference TEXT)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT p_reference IS NULL OR (
    length(p_reference) BETWEEN 8 AND 1024
    AND p_reference ~ '^(vault|env|kms|secret|provider-ref|opaque-ref):'
    AND p_reference !~ '[[:space:]]'
  );
$$;

CREATE OR REPLACE FUNCTION a1_oauth_public_metadata(p_metadata JSONB)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  item RECORD;
  normalized_key TEXT;
BEGIN
  IF p_metadata IS NULL OR jsonb_typeof(p_metadata) IN ('null', 'string', 'number', 'boolean') THEN
    RETURN TRUE;
  END IF;
  IF jsonb_typeof(p_metadata) = 'array' THEN
    FOR item IN SELECT value FROM jsonb_array_elements(p_metadata)
    LOOP
      IF NOT a1_oauth_public_metadata(item.value) THEN
        RETURN FALSE;
      END IF;
    END LOOP;
    RETURN TRUE;
  END IF;
  IF jsonb_typeof(p_metadata) <> 'object' THEN
    RETURN FALSE;
  END IF;
  FOR item IN SELECT key, value FROM jsonb_each(p_metadata)
  LOOP
    normalized_key := lower(regexp_replace(item.key, '[^a-zA-Z0-9]', '', 'g'));
    IF normalized_key IN (
      'accesstoken',
      'refreshtoken',
      'idtoken',
      'authorizationcode',
      'rawcode',
      'codeverifier',
      'clientsecret',
      'state',
      'nonce',
      'password',
      'cookie'
    ) THEN
      RETURN FALSE;
    END IF;
    IF NOT a1_oauth_public_metadata(item.value) THEN
      RETURN FALSE;
    END IF;
  END LOOP;
  RETURN TRUE;
END;
$$;

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'suspended', 'deleted')),
  email_digest TEXT,
  display_name TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_oauth_public_metadata(metadata)),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ,
  CONSTRAINT users_digest_format CHECK (
    email_digest IS NULL OR email_digest ~ '^[a-f0-9]{64}$'
  ),
  CONSTRAINT users_org_project_id_key UNIQUE (organization_id, project_id, id),
  CONSTRAINT users_project_scope_fk FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS users_active_email_digest_key
  ON users(organization_id, project_id, email_digest)
  WHERE email_digest IS NOT NULL AND deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS oauth_attempts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  provider TEXT NOT NULL,
  environment TEXT NOT NULL CHECK (environment IN ('sandbox', 'live')),
  purpose TEXT NOT NULL CHECK (purpose IN ('login', 'link')),
  requested_user_id UUID,
  redirect_uri_digest TEXT NOT NULL CHECK (redirect_uri_digest ~ '^[a-f0-9]{64}$'),
  state_digest TEXT NOT NULL CHECK (state_digest ~ '^[a-f0-9]{64}$'),
  code_digest TEXT CHECK (code_digest IS NULL OR code_digest ~ '^[a-f0-9]{64}$'),
  pkce_challenge_digest TEXT NOT NULL CHECK (pkce_challenge_digest ~ '^[a-f0-9]{64}$'),
  nonce_digest TEXT CHECK (nonce_digest IS NULL OR nonce_digest ~ '^[a-f0-9]{64}$'),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'consumed', 'failed', 'expired')),
  failure_code TEXT,
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT oauth_attempts_ttl_check CHECK (expires_at > created_at),
  CONSTRAINT oauth_attempts_link_target_check CHECK (
    purpose = 'login' OR requested_user_id IS NOT NULL
  ),
  CONSTRAINT oauth_attempts_consumption_check CHECK (
    (status = 'consumed' AND consumed_at IS NOT NULL AND code_digest IS NOT NULL)
    OR (status <> 'consumed' AND consumed_at IS NULL)
  ),
  CONSTRAINT oauth_attempts_org_project_id_key UNIQUE (organization_id, project_id, id),
  CONSTRAINT oauth_attempts_state_key UNIQUE (
    organization_id, project_id, provider, environment, state_digest
  ),
  CONSTRAINT oauth_attempts_requested_user_fk FOREIGN KEY (
    organization_id, project_id, requested_user_id
  ) REFERENCES users(organization_id, project_id, id) ON DELETE RESTRICT,
  CONSTRAINT oauth_attempts_project_scope_fk FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS oauth_attempts_consumed_code_key
  ON oauth_attempts(organization_id, project_id, provider, environment, code_digest)
  WHERE code_digest IS NOT NULL;
CREATE INDEX IF NOT EXISTS oauth_attempts_pending_expiry_idx
  ON oauth_attempts(organization_id, project_id, expires_at)
  WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS external_identities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  user_id UUID NOT NULL,
  provider TEXT NOT NULL,
  environment TEXT NOT NULL CHECK (environment IN ('sandbox', 'live')),
  subject_digest TEXT NOT NULL CHECK (subject_digest ~ '^[a-f0-9]{64}$'),
  account_binding_digest TEXT
    CHECK (account_binding_digest IS NULL OR account_binding_digest ~ '^[a-f0-9]{64}$'),
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'revoked')),
  linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_authenticated_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_oauth_public_metadata(metadata)),
  CONSTRAINT external_identities_revocation_check CHECK (
    (status = 'revoked' AND revoked_at IS NOT NULL)
    OR (status = 'active' AND revoked_at IS NULL)
  ),
  CONSTRAINT external_identities_org_project_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT external_identities_provider_subject_key
    UNIQUE (organization_id, project_id, provider, environment, subject_digest),
  CONSTRAINT external_identities_user_provider_key
    UNIQUE (organization_id, project_id, user_id, provider, environment),
  CONSTRAINT external_identities_user_scope_fk FOREIGN KEY (
    organization_id, project_id, user_id
  ) REFERENCES users(organization_id, project_id, id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  user_id UUID NOT NULL,
  external_identity_id UUID,
  session_digest TEXT NOT NULL CHECK (session_digest ~ '^[a-f0-9]{64}$'),
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'revoked', 'expired')),
  authenticated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  last_seen_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_oauth_public_metadata(metadata)),
  CONSTRAINT sessions_ttl_check CHECK (expires_at > authenticated_at),
  CONSTRAINT sessions_revocation_check CHECK (
    (status = 'revoked' AND revoked_at IS NOT NULL)
    OR (status <> 'revoked' AND revoked_at IS NULL)
  ),
  CONSTRAINT sessions_org_project_id_key UNIQUE (organization_id, project_id, id),
  CONSTRAINT sessions_identity_id_key UNIQUE (
    organization_id, project_id, external_identity_id, id
  ),
  CONSTRAINT sessions_digest_key UNIQUE (organization_id, project_id, session_digest),
  CONSTRAINT sessions_user_scope_fk FOREIGN KEY (organization_id, project_id, user_id)
    REFERENCES users(organization_id, project_id, id) ON DELETE RESTRICT,
  CONSTRAINT sessions_identity_scope_fk FOREIGN KEY (
    organization_id, project_id, external_identity_id
  ) REFERENCES external_identities(organization_id, project_id, id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS sessions_active_expiry_idx
  ON sessions(organization_id, project_id, expires_at)
  WHERE status = 'active';

CREATE TABLE IF NOT EXISTS token_secret_refs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  external_identity_id UUID NOT NULL,
  session_id UUID,
  secret_kind TEXT NOT NULL
    CHECK (secret_kind IN ('access', 'refresh', 'id_assertion')),
  secret_ref TEXT NOT NULL CHECK (a1_oauth_reference_only(secret_ref)),
  secret_fingerprint TEXT
    CHECK (secret_fingerprint IS NULL OR secret_fingerprint ~ '^[a-f0-9]{64}$'),
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'rotated', 'revoked', 'expired')),
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  rotated_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  CONSTRAINT token_secret_refs_status_time_check CHECK (
    (status = 'revoked' AND revoked_at IS NOT NULL)
    OR status <> 'revoked'
  ),
  CONSTRAINT token_secret_refs_identity_kind_key UNIQUE NULLS NOT DISTINCT (
    organization_id, project_id, external_identity_id, session_id, secret_kind
  ),
  CONSTRAINT token_secret_refs_identity_scope_fk FOREIGN KEY (
    organization_id, project_id, external_identity_id
  ) REFERENCES external_identities(organization_id, project_id, id) ON DELETE RESTRICT,
  CONSTRAINT token_secret_refs_session_identity_scope_fk FOREIGN KEY (
    organization_id, project_id, external_identity_id, session_id
  ) REFERENCES sessions(
    organization_id, project_id, external_identity_id, id
  ) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS oauth_revocations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  external_identity_id UUID,
  session_id UUID,
  reason_code TEXT NOT NULL,
  actor_ref TEXT,
  request_id TEXT,
  revoked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_oauth_public_metadata(metadata)),
  CONSTRAINT oauth_revocations_target_check CHECK (
    external_identity_id IS NOT NULL OR session_id IS NOT NULL
  ),
  CONSTRAINT oauth_revocations_identity_scope_fk FOREIGN KEY (
    organization_id, project_id, external_identity_id
  ) REFERENCES external_identities(organization_id, project_id, id) ON DELETE RESTRICT,
  CONSTRAINT oauth_revocations_session_scope_fk FOREIGN KEY (
    organization_id, project_id, session_id
  ) REFERENCES sessions(organization_id, project_id, id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS oauth_audit_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  actor_ref TEXT,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id UUID,
  request_id TEXT,
  event_digest TEXT NOT NULL CHECK (event_digest ~ '^[a-f0-9]{64}$'),
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_oauth_public_metadata(metadata)),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT oauth_audit_events_digest_key UNIQUE (
    organization_id, project_id, event_digest
  ),
  CONSTRAINT oauth_audit_events_project_scope_fk FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS oauth_audit_events_scope_created_idx
  ON oauth_audit_events(organization_id, project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS oauth_outbox (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  event_type TEXT NOT NULL,
  aggregate_type TEXT NOT NULL,
  aggregate_id UUID NOT NULL,
  event_digest TEXT NOT NULL CHECK (event_digest ~ '^[a-f0-9]{64}$'),
  payload JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_oauth_public_metadata(payload)),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'delivering', 'delivered', 'dead_letter')),
  available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  delivered_at TIMESTAMPTZ,
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT oauth_outbox_digest_key UNIQUE (
    organization_id, project_id, event_digest
  ),
  CONSTRAINT oauth_outbox_delivery_check CHECK (
    (status = 'delivered' AND delivered_at IS NOT NULL)
    OR (status <> 'delivered' AND delivered_at IS NULL)
  ),
  CONSTRAINT oauth_outbox_project_scope_fk FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS oauth_outbox_delivery_idx
  ON oauth_outbox(available_at, created_at)
  WHERE status = 'pending';

CREATE OR REPLACE FUNCTION a1_oauth_assert_runtime_context(
  p_organization_id UUID,
  p_project_id UUID
)
RETURNS VOID
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
  PERFORM a1_assert_role_nobypassrls(current_user);
  IF p_organization_id IS DISTINCT FROM a1_current_organization_id()
     OR p_project_id IS DISTINCT FROM a1_current_project_id() THEN
    RAISE EXCEPTION 'oauth tenant context mismatch'
      USING ERRCODE = '42501';
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION a1_oauth_reject_append_only_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION '% is append only', TG_TABLE_NAME
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION a1_oauth_reject_hard_delete()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION '% must use OAuth lifecycle status transitions', TG_TABLE_NAME
    USING ERRCODE = '55000';
END;
$$;

DROP TRIGGER IF EXISTS users_reject_hard_delete ON users;
CREATE TRIGGER users_reject_hard_delete
BEFORE DELETE ON users
FOR EACH ROW EXECUTE FUNCTION a1_oauth_reject_hard_delete();

DROP TRIGGER IF EXISTS external_identities_reject_hard_delete ON external_identities;
CREATE TRIGGER external_identities_reject_hard_delete
BEFORE DELETE ON external_identities
FOR EACH ROW EXECUTE FUNCTION a1_oauth_reject_hard_delete();

DROP TRIGGER IF EXISTS sessions_reject_hard_delete ON sessions;
CREATE TRIGGER sessions_reject_hard_delete
BEFORE DELETE ON sessions
FOR EACH ROW EXECUTE FUNCTION a1_oauth_reject_hard_delete();

DROP TRIGGER IF EXISTS token_secret_refs_reject_hard_delete ON token_secret_refs;
CREATE TRIGGER token_secret_refs_reject_hard_delete
BEFORE DELETE ON token_secret_refs
FOR EACH ROW EXECUTE FUNCTION a1_oauth_reject_hard_delete();

DROP TRIGGER IF EXISTS oauth_revocations_append_only ON oauth_revocations;
CREATE TRIGGER oauth_revocations_append_only
BEFORE UPDATE OR DELETE ON oauth_revocations
FOR EACH ROW EXECUTE FUNCTION a1_oauth_reject_append_only_mutation();

DROP TRIGGER IF EXISTS oauth_audit_events_append_only ON oauth_audit_events;
CREATE TRIGGER oauth_audit_events_append_only
BEFORE UPDATE OR DELETE ON oauth_audit_events
FOR EACH ROW EXECUTE FUNCTION a1_oauth_reject_append_only_mutation();

CREATE OR REPLACE FUNCTION a1_consume_oauth_attempt(
  p_organization_id UUID,
  p_project_id UUID,
  p_attempt_id UUID,
  p_state_digest TEXT,
  p_code_digest TEXT,
  p_consumed_at TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS oauth_attempts
LANGUAGE plpgsql
AS $$
DECLARE
  attempt oauth_attempts%ROWTYPE;
BEGIN
  PERFORM a1_oauth_assert_runtime_context(p_organization_id, p_project_id);
  IF p_state_digest !~ '^[a-f0-9]{64}$'
     OR p_code_digest !~ '^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION 'oauth callback digests must be sha256 hex'
      USING ERRCODE = '22023';
  END IF;

  SELECT *
    INTO attempt
    FROM oauth_attempts
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_attempt_id
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'oauth attempt not found in tenant scope'
      USING ERRCODE = 'P0002';
  END IF;
  IF attempt.status <> 'pending' OR attempt.consumed_at IS NOT NULL THEN
    RAISE EXCEPTION 'oauth attempt already consumed or closed'
      USING ERRCODE = '23505';
  END IF;
  IF attempt.expires_at <= p_consumed_at THEN
    RAISE EXCEPTION 'oauth attempt expired'
      USING ERRCODE = '22023';
  END IF;
  IF attempt.state_digest <> p_state_digest THEN
    RAISE EXCEPTION 'oauth state digest mismatch'
      USING ERRCODE = '22023';
  END IF;

  UPDATE oauth_attempts
     SET status = 'consumed',
         code_digest = p_code_digest,
         consumed_at = p_consumed_at,
         failure_code = NULL
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_attempt_id
  RETURNING * INTO attempt;
  RETURN attempt;
END;
$$;

CREATE OR REPLACE FUNCTION a1_link_oauth_identity(
  p_organization_id UUID,
  p_project_id UUID,
  p_attempt_id UUID,
  p_state_digest TEXT,
  p_code_digest TEXT,
  p_subject_digest TEXT,
  p_account_binding_digest TEXT,
  p_session_digest TEXT,
  p_session_expires_at TIMESTAMPTZ,
  p_email_digest TEXT DEFAULT NULL,
  p_access_secret_ref TEXT DEFAULT NULL,
  p_refresh_secret_ref TEXT DEFAULT NULL,
  p_actor_ref TEXT DEFAULT NULL,
  p_request_id TEXT DEFAULT NULL,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE (
  user_id UUID,
  external_identity_id UUID,
  session_id UUID
)
LANGUAGE plpgsql
AS $$
DECLARE
  attempt oauth_attempts%ROWTYPE;
  identity external_identities%ROWTYPE;
  linked_user users%ROWTYPE;
  issued_session sessions%ROWTYPE;
  event_seed TEXT;
BEGIN
  PERFORM a1_oauth_assert_runtime_context(p_organization_id, p_project_id);
  IF p_subject_digest !~ '^[a-f0-9]{64}$'
     OR p_session_digest !~ '^[a-f0-9]{64}$'
     OR (p_account_binding_digest IS NOT NULL
         AND p_account_binding_digest !~ '^[a-f0-9]{64}$')
     OR (p_email_digest IS NOT NULL AND p_email_digest !~ '^[a-f0-9]{64}$') THEN
    RAISE EXCEPTION 'oauth identity digests must be sha256 hex'
      USING ERRCODE = '22023';
  END IF;
  IF NOT a1_oauth_public_metadata(p_metadata)
     OR NOT a1_oauth_reference_only(p_access_secret_ref)
     OR NOT a1_oauth_reference_only(p_refresh_secret_ref) THEN
    RAISE EXCEPTION 'oauth metadata or secret reference rejected'
      USING ERRCODE = '22023';
  END IF;

  attempt := a1_consume_oauth_attempt(
    p_organization_id,
    p_project_id,
    p_attempt_id,
    p_state_digest,
    p_code_digest
  );

  SELECT *
    INTO identity
    FROM external_identities
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND provider = attempt.provider
     AND environment = attempt.environment
     AND subject_digest = p_subject_digest
   FOR UPDATE;

  IF FOUND THEN
    IF identity.status <> 'active' THEN
      RAISE EXCEPTION 'oauth identity is revoked'
        USING ERRCODE = '42501';
    END IF;
    IF attempt.requested_user_id IS NOT NULL
       AND identity.user_id <> attempt.requested_user_id THEN
      RAISE EXCEPTION 'oauth identity is already linked to another account'
        USING ERRCODE = '23505';
    END IF;
    UPDATE external_identities
       SET last_authenticated_at = clock_timestamp(),
           account_binding_digest = COALESCE(
             p_account_binding_digest,
             account_binding_digest
           )
     WHERE organization_id = p_organization_id
       AND project_id = p_project_id
       AND id = identity.id
    RETURNING * INTO identity;
  ELSE
    IF attempt.requested_user_id IS NOT NULL THEN
      SELECT *
        INTO linked_user
        FROM users
       WHERE organization_id = p_organization_id
         AND project_id = p_project_id
         AND id = attempt.requested_user_id
         AND status = 'active'
       FOR UPDATE;
      IF NOT FOUND THEN
        RAISE EXCEPTION 'requested oauth account is not active'
          USING ERRCODE = 'P0002';
      END IF;
    ELSE
      BEGIN
        INSERT INTO users (
          organization_id,
          project_id,
          email_digest,
          metadata
        ) VALUES (
          p_organization_id,
          p_project_id,
          p_email_digest,
          p_metadata
        )
        RETURNING * INTO linked_user;
      EXCEPTION WHEN unique_violation THEN
        RAISE EXCEPTION 'oauth account conflicts with an existing account'
          USING ERRCODE = '23505';
      END;
    END IF;

    BEGIN
      INSERT INTO external_identities (
        organization_id,
        project_id,
        user_id,
        provider,
        environment,
        subject_digest,
        account_binding_digest,
        last_authenticated_at,
        metadata
      ) VALUES (
        p_organization_id,
        p_project_id,
        linked_user.id,
        attempt.provider,
        attempt.environment,
        p_subject_digest,
        p_account_binding_digest,
        clock_timestamp(),
        p_metadata
      )
      RETURNING * INTO identity;
    EXCEPTION WHEN unique_violation THEN
      RAISE EXCEPTION 'oauth identity conflicts with an existing account'
        USING ERRCODE = '23505';
    END;
  END IF;

  SELECT *
    INTO linked_user
    FROM users
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = identity.user_id
     AND status = 'active'
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'oauth account is not active'
      USING ERRCODE = '42501';
  END IF;

  INSERT INTO sessions (
    organization_id,
    project_id,
    user_id,
    external_identity_id,
    session_digest,
    expires_at,
    metadata
  ) VALUES (
    p_organization_id,
    p_project_id,
    linked_user.id,
    identity.id,
    p_session_digest,
    p_session_expires_at,
    p_metadata
  )
  RETURNING * INTO issued_session;

  IF p_access_secret_ref IS NOT NULL THEN
    INSERT INTO token_secret_refs (
      organization_id, project_id, external_identity_id, session_id,
      secret_kind, secret_ref
    ) VALUES (
      p_organization_id, p_project_id, identity.id, issued_session.id,
      'access', p_access_secret_ref
    );
  END IF;
  IF p_refresh_secret_ref IS NOT NULL THEN
    INSERT INTO token_secret_refs (
      organization_id, project_id, external_identity_id, session_id,
      secret_kind, secret_ref
    ) VALUES (
      p_organization_id, p_project_id, identity.id, issued_session.id,
      'refresh', p_refresh_secret_ref
    );
  END IF;

  event_seed := concat_ws(
    ':', p_organization_id, p_project_id, p_attempt_id, identity.id,
    issued_session.id, 'oauth.identity.linked'
  );
  INSERT INTO oauth_audit_events (
    organization_id, project_id, actor_ref, action, resource_type,
    resource_id, request_id, event_digest, metadata
  ) VALUES (
    p_organization_id, p_project_id, p_actor_ref, 'oauth.identity.linked',
    'external_identity', identity.id, p_request_id,
    a1_oauth_digest(event_seed || ':audit'), p_metadata
  );
  INSERT INTO oauth_outbox (
    organization_id, project_id, event_type, aggregate_type,
    aggregate_id, event_digest, payload
  ) VALUES (
    p_organization_id, p_project_id, 'oauth.identity.linked',
    'external_identity', identity.id,
    a1_oauth_digest(event_seed || ':outbox'),
    jsonb_build_object(
      'provider', attempt.provider,
      'environment', attempt.environment,
      'user_id', linked_user.id,
      'session_id', issued_session.id
    )
  );

  RETURN QUERY SELECT linked_user.id, identity.id, issued_session.id;
END;
$$;

CREATE OR REPLACE FUNCTION a1_revoke_oauth_identity(
  p_organization_id UUID,
  p_project_id UUID,
  p_external_identity_id UUID,
  p_reason_code TEXT,
  p_actor_ref TEXT DEFAULT NULL,
  p_request_id TEXT DEFAULT NULL,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS oauth_revocations
LANGUAGE plpgsql
AS $$
DECLARE
  identity external_identities%ROWTYPE;
  revocation oauth_revocations%ROWTYPE;
  event_seed TEXT;
  revoked_at_value TIMESTAMPTZ := clock_timestamp();
BEGIN
  PERFORM a1_oauth_assert_runtime_context(p_organization_id, p_project_id);
  IF p_reason_code IS NULL OR btrim(p_reason_code) = ''
     OR NOT a1_oauth_public_metadata(p_metadata) THEN
    RAISE EXCEPTION 'oauth revocation reason and safe metadata are required'
      USING ERRCODE = '22023';
  END IF;

  SELECT *
    INTO identity
    FROM external_identities
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_external_identity_id
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'oauth identity not found in tenant scope'
      USING ERRCODE = 'P0002';
  END IF;
  IF identity.status = 'revoked' THEN
    RAISE EXCEPTION 'oauth identity already revoked'
      USING ERRCODE = '23505';
  END IF;

  UPDATE external_identities
     SET status = 'revoked',
         revoked_at = revoked_at_value
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = identity.id;
  UPDATE sessions
     SET status = 'revoked',
         revoked_at = revoked_at_value
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND external_identity_id = identity.id
     AND status = 'active';
  UPDATE token_secret_refs
     SET status = 'revoked',
         revoked_at = revoked_at_value
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND external_identity_id = identity.id
     AND status IN ('active', 'rotated');

  INSERT INTO oauth_revocations (
    organization_id, project_id, external_identity_id, reason_code,
    actor_ref, request_id, revoked_at, metadata
  ) VALUES (
    p_organization_id, p_project_id, identity.id, p_reason_code,
    p_actor_ref, p_request_id, revoked_at_value, p_metadata
  )
  RETURNING * INTO revocation;

  event_seed := concat_ws(
    ':', p_organization_id, p_project_id, identity.id,
    revocation.id, 'oauth.identity.revoked'
  );
  INSERT INTO oauth_audit_events (
    organization_id, project_id, actor_ref, action, resource_type,
    resource_id, request_id, event_digest, metadata
  ) VALUES (
    p_organization_id, p_project_id, p_actor_ref, 'oauth.identity.revoked',
    'external_identity', identity.id, p_request_id,
    a1_oauth_digest(event_seed || ':audit'),
    p_metadata || jsonb_build_object('reason_code', p_reason_code)
  );
  INSERT INTO oauth_outbox (
    organization_id, project_id, event_type, aggregate_type,
    aggregate_id, event_digest, payload
  ) VALUES (
    p_organization_id, p_project_id, 'oauth.identity.revoked',
    'external_identity', identity.id,
    a1_oauth_digest(event_seed || ':outbox'),
    jsonb_build_object(
      'reason_code', p_reason_code,
      'revocation_id', revocation.id
    )
  );

  RETURN revocation;
END;
$$;

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE external_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE token_secret_refs ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_revocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_outbox ENABLE ROW LEVEL SECURITY;

ALTER TABLE users FORCE ROW LEVEL SECURITY;
ALTER TABLE oauth_attempts FORCE ROW LEVEL SECURITY;
ALTER TABLE external_identities FORCE ROW LEVEL SECURITY;
ALTER TABLE sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE token_secret_refs FORCE ROW LEVEL SECURITY;
ALTER TABLE oauth_revocations FORCE ROW LEVEL SECURITY;
ALTER TABLE oauth_audit_events FORCE ROW LEVEL SECURITY;
ALTER TABLE oauth_outbox FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS users_tenant_isolation ON users;
DROP POLICY IF EXISTS oauth_attempts_tenant_isolation ON oauth_attempts;
DROP POLICY IF EXISTS external_identities_tenant_isolation ON external_identities;
DROP POLICY IF EXISTS sessions_tenant_isolation ON sessions;
DROP POLICY IF EXISTS token_secret_refs_tenant_isolation ON token_secret_refs;
DROP POLICY IF EXISTS oauth_revocations_tenant_isolation ON oauth_revocations;
DROP POLICY IF EXISTS oauth_audit_events_tenant_isolation ON oauth_audit_events;
DROP POLICY IF EXISTS oauth_outbox_tenant_isolation ON oauth_outbox;

CREATE POLICY users_tenant_isolation ON users
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY oauth_attempts_tenant_isolation ON oauth_attempts
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY external_identities_tenant_isolation ON external_identities
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY sessions_tenant_isolation ON sessions
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY token_secret_refs_tenant_isolation ON token_secret_refs
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY oauth_revocations_tenant_isolation ON oauth_revocations
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY oauth_audit_events_tenant_isolation ON oauth_audit_events
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());
CREATE POLICY oauth_outbox_tenant_isolation ON oauth_outbox
  USING (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id())
  WITH CHECK (organization_id = a1_current_organization_id() AND project_id = a1_current_project_id());

COMMIT;
