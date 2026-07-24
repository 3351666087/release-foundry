-- Atomic OAuth first-login to canonical account and browser session handoff.
-- Provider subjects, verified emails, browser bearers, and OAuth tokens never
-- enter PostgreSQL in raw form. The only OAuth secret value stored here is an
-- opaque reference to an external vault.

BEGIN;

CREATE TABLE IF NOT EXISTS oauth_first_login_operations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  provider TEXT NOT NULL CHECK (provider IN ('google', 'github')),
  subject_digest TEXT NOT NULL
    CHECK (a1_identity_digest_valid(subject_digest)),
  idempotency_digest TEXT NOT NULL
    CHECK (a1_identity_digest_valid(idempotency_digest)),
  request_digest TEXT NOT NULL
    CHECK (a1_identity_digest_valid(request_digest)),
  principal_id UUID,
  credential_id UUID,
  connection_id UUID,
  token_ref_id UUID,
  session_id UUID,
  account_created BOOLEAN,
  status TEXT NOT NULL DEFAULT 'processing'
    CHECK (status IN ('processing', 'completed')),
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT oauth_first_login_operations_scope_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT oauth_first_login_operations_idempotency_key
    UNIQUE (
      organization_id, project_id, provider, idempotency_digest
    ),
  CONSTRAINT oauth_first_login_operations_project_scope_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT oauth_first_login_operations_principal_fk
    FOREIGN KEY (principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT oauth_first_login_operations_credential_scope_fk
    FOREIGN KEY (principal_id, credential_id)
    REFERENCES identity_credentials(principal_id, id) ON DELETE RESTRICT,
  CONSTRAINT oauth_first_login_operations_connection_scope_fk
    FOREIGN KEY (organization_id, project_id, connection_id)
    REFERENCES oauth_account_connections(
      organization_id, project_id, id
    ) ON DELETE RESTRICT,
  CONSTRAINT oauth_first_login_operations_token_scope_fk
    FOREIGN KEY (organization_id, project_id, token_ref_id)
    REFERENCES oauth_token_opaque_refs(
      organization_id, project_id, id
    ) ON DELETE RESTRICT,
  CONSTRAINT oauth_first_login_operations_session_fk
    FOREIGN KEY (session_id)
    REFERENCES identity_sessions(id) ON DELETE RESTRICT,
  CONSTRAINT oauth_first_login_operations_completion_check CHECK (
    (
      status = 'processing'
      AND principal_id IS NULL
      AND credential_id IS NULL
      AND connection_id IS NULL
      AND token_ref_id IS NULL
      AND session_id IS NULL
      AND account_created IS NULL
      AND completed_at IS NULL
    )
    OR (
      status = 'completed'
      AND principal_id IS NOT NULL
      AND credential_id IS NOT NULL
      AND connection_id IS NOT NULL
      AND token_ref_id IS NOT NULL
      AND session_id IS NOT NULL
      AND account_created IS NOT NULL
      AND completed_at IS NOT NULL
    )
  )
);

CREATE INDEX IF NOT EXISTS oauth_first_login_operations_subject_created_idx
  ON oauth_first_login_operations(
    provider, subject_digest, created_at DESC
  );

CREATE OR REPLACE FUNCTION a1_complete_oauth_first_login_with_refresh(
  p_organization_id UUID,
  p_project_id UUID,
  p_provider TEXT,
  p_subject_digests TEXT[],
  p_email_digests TEXT[],
  p_opaque_ref TEXT,
  p_opaque_ref_digest TEXT,
  p_binding_digest TEXT,
  p_session_digest TEXT,
  p_refresh_digest TEXT,
  p_rotation_family_digest TEXT,
  p_access_expires_at TIMESTAMPTZ,
  p_refresh_expires_at TIMESTAMPTZ,
  p_idempotency_digest TEXT,
  p_request_digest TEXT,
  p_display_label TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE (
  session_id UUID,
  principal_id UUID,
  credential_id UUID,
  connection_id UUID,
  token_ref_id UUID,
  created BOOLEAN,
  organization_id UUID,
  project_id UUID,
  provider_name TEXT,
  access_expires_at TIMESTAMPTZ,
  refresh_expires_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  operation oauth_first_login_operations%ROWTYPE;
  principal identity_principals%ROWTYPE;
  credential identity_credentials%ROWTYPE;
  connection oauth_account_connections%ROWTYPE;
  token_ref oauth_token_opaque_refs%ROWTYPE;
  previous_token_ref oauth_token_opaque_refs%ROWTYPE;
  v_now TIMESTAMPTZ := clock_timestamp();
  v_principal_id UUID;
  v_credential_id UUID;
  v_connection_id UUID;
  v_token_ref_id UUID;
  v_session_id UUID;
  v_organization_membership_id UUID;
  v_email_owner UUID;
  v_existing_email_digest TEXT;
  v_active_subject_digest TEXT;
  v_active_email_digest TEXT;
  v_lock_digest TEXT;
  v_subject_match_count BIGINT;
  v_subject_principal_count BIGINT;
  v_connection_match_count BIGINT;
  v_created BOOLEAN := FALSE;
BEGIN
  PERFORM a1_assert_role_nobypassrls(session_user);

  v_active_subject_digest := p_subject_digests[1];
  IF cardinality(p_email_digests) > 0 THEN
    v_active_email_digest := p_email_digests[1];
  END IF;

  IF p_organization_id IS NULL
     OR p_project_id IS NULL
     OR p_organization_id IS DISTINCT FROM a1_current_organization_id()
     OR p_project_id IS DISTINCT FROM a1_current_project_id()
     OR NOT EXISTS (
       SELECT 1
         FROM organizations AS organization
         JOIN projects AS project
           ON project.organization_id = organization.id
          AND project.id = p_project_id
          AND project.status = 'active'
        WHERE organization.id = p_organization_id
          AND organization.status = 'active'
     ) THEN
    RAISE EXCEPTION 'oauth first-login trusted scope is unavailable'
      USING ERRCODE = '42501';
  END IF;

  IF p_provider NOT IN ('google', 'github')
     OR p_subject_digests IS NULL
     OR cardinality(p_subject_digests) NOT BETWEEN 1 AND 16
     OR array_position(p_subject_digests, NULL) IS NOT NULL
     OR EXISTS (
       SELECT 1
         FROM unnest(p_subject_digests) AS subject_candidate(digest)
        WHERE NOT a1_identity_digest_valid(subject_candidate.digest)
     )
     OR (
       SELECT count(DISTINCT subject_candidate.digest)
         FROM unnest(p_subject_digests) AS subject_candidate(digest)
     ) <> cardinality(p_subject_digests)
     OR p_email_digests IS NULL
     OR cardinality(p_email_digests) NOT BETWEEN 0 AND 16
     OR array_position(p_email_digests, NULL) IS NOT NULL
     OR EXISTS (
       SELECT 1
         FROM unnest(p_email_digests) AS email_candidate(digest)
        WHERE NOT a1_identity_digest_valid(email_candidate.digest)
     )
     OR (
       SELECT count(DISTINCT email_candidate.digest)
         FROM unnest(p_email_digests) AS email_candidate(digest)
     ) <> cardinality(p_email_digests)
     OR NOT a1_oauth_reference_only(p_opaque_ref)
     OR NOT a1_identity_digest_valid(p_opaque_ref_digest)
     OR NOT a1_identity_digest_valid(p_binding_digest)
     OR NOT a1_identity_digest_valid(p_session_digest)
     OR NOT a1_identity_digest_valid(p_refresh_digest)
     OR NOT a1_identity_digest_valid(p_rotation_family_digest)
     OR NOT a1_identity_digest_valid(p_idempotency_digest)
     OR NOT a1_identity_digest_valid(p_request_digest)
     OR p_session_digest = p_refresh_digest
     OR p_access_expires_at <= v_now
     OR p_refresh_expires_at <= p_access_expires_at
     OR length(COALESCE(p_display_label, '')) > 256
     OR COALESCE(p_display_label, '') <>
          btrim(COALESCE(p_display_label, ''))
     OR COALESCE(p_display_label, '') ~ '[\r\n]'
     OR NOT a1_identity_public_metadata(p_metadata)
     OR NOT a1_oauth_public_metadata(p_metadata) THEN
    RAISE EXCEPTION 'oauth first-login input rejected'
      USING ERRCODE = '22023';
  END IF;

  INSERT INTO oauth_first_login_operations (
    organization_id,
    project_id,
    provider,
    subject_digest,
    idempotency_digest,
    request_digest
  ) VALUES (
    p_organization_id,
    p_project_id,
    p_provider,
    v_active_subject_digest,
    p_idempotency_digest,
    p_request_digest
  )
  ON CONFLICT ON CONSTRAINT
    oauth_first_login_operations_idempotency_key
  DO NOTHING;

  SELECT operation_row.*
    INTO operation
    FROM oauth_first_login_operations AS operation_row
   WHERE operation_row.organization_id = p_organization_id
     AND operation_row.project_id = p_project_id
     AND operation_row.provider = p_provider
     AND operation_row.idempotency_digest = p_idempotency_digest
   FOR UPDATE;
  IF operation.request_digest <> p_request_digest
     OR operation.subject_digest <> v_active_subject_digest THEN
    RAISE EXCEPTION 'idempotency_conflict'
      USING ERRCODE = '23505';
  END IF;
  IF operation.status = 'completed' THEN
    RETURN QUERY SELECT
      operation.session_id,
      operation.principal_id,
      operation.credential_id,
      operation.connection_id,
      operation.token_ref_id,
      operation.account_created,
      session_row.organization_id,
      session_row.project_id,
      p_provider,
      session_row.expires_at,
      session_row.refresh_expires_at,
      operation.completed_at
    FROM identity_sessions AS session_row
    WHERE session_row.id = operation.session_id
      AND session_row.principal_id = operation.principal_id
      AND session_row.credential_id = operation.credential_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'oauth first-login replay session is unavailable'
        USING ERRCODE = '40001';
    END IF;
    RETURN;
  END IF;

  -- Different callbacks for one provider subject serialize before the
  -- absent-row lookup, so two first-login transactions cannot create two
  -- canonical principals for the same external identity.
  FOR v_lock_digest IN
    SELECT DISTINCT subject_candidate.digest
      FROM unnest(p_subject_digests) AS subject_candidate(digest)
     ORDER BY subject_candidate.digest
  LOOP
    PERFORM pg_advisory_xact_lock(
      8101,
      hashtext(p_provider || ':production:' || v_lock_digest)
    );
  END LOOP;

  PERFORM 1
    FROM identity_credentials AS credential_row
   WHERE credential_row.provider = p_provider
     AND credential_row.provider_environment = 'production'
     AND credential_row.subject_digest = ANY(p_subject_digests)
   ORDER BY array_position(
     p_subject_digests,
     credential_row.subject_digest
   )
   FOR UPDATE;

  SELECT
    count(*),
    count(DISTINCT credential_row.principal_id)
    INTO v_subject_match_count, v_subject_principal_count
    FROM identity_credentials AS credential_row
   WHERE credential_row.provider = p_provider
     AND credential_row.provider_environment = 'production'
     AND credential_row.subject_digest = ANY(p_subject_digests);
  IF v_subject_match_count > 1 OR v_subject_principal_count > 1 THEN
    RAISE EXCEPTION 'oauth subject digest candidates are ambiguous'
      USING ERRCODE = '23505';
  END IF;

  SELECT credential_row.*
    INTO credential
    FROM identity_credentials AS credential_row
   WHERE credential_row.provider = p_provider
     AND credential_row.provider_environment = 'production'
     AND credential_row.subject_digest = ANY(p_subject_digests)
   ORDER BY array_position(
     p_subject_digests,
     credential_row.subject_digest
   )
   LIMIT 1
   FOR UPDATE;
  IF FOUND THEN
    SELECT principal_row.*
      INTO principal
      FROM identity_principals AS principal_row
     WHERE principal_row.id = credential.principal_id
     FOR UPDATE;
    IF NOT FOUND
       OR principal.status <> 'active'
       OR credential.status <> 'active'
       OR NOT credential.login_enabled THEN
      RAISE EXCEPTION 'oauth first-login canonical account is unavailable'
        USING ERRCODE = '42501';
    END IF;

    SELECT organization_membership.id
      INTO v_organization_membership_id
      FROM identity_organization_memberships AS organization_membership
      JOIN identity_project_memberships AS project_membership
        ON project_membership.organization_id =
             organization_membership.organization_id
       AND project_membership.organization_membership_id =
             organization_membership.id
       AND project_membership.principal_id =
             organization_membership.principal_id
       AND project_membership.project_id = p_project_id
       AND project_membership.status = 'active'
     WHERE organization_membership.organization_id = p_organization_id
       AND organization_membership.principal_id = credential.principal_id
       AND organization_membership.status = 'active'
     FOR KEY SHARE OF organization_membership, project_membership;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'oauth first-login canonical scope is unavailable'
        USING ERRCODE = '42501';
    END IF;

    v_principal_id := principal.id;
    v_credential_id := credential.id;
    v_created := FALSE;

    UPDATE identity_credentials AS credential_row
       SET subject_digest = v_active_subject_digest,
           last_authenticated_at = v_now,
           metadata = credential_row.metadata || p_metadata,
           updated_at = v_now
     WHERE credential_row.id = credential.id;
  ELSE
    INSERT INTO identity_principals (
      status,
      display_label,
      metadata,
      created_at,
      updated_at
    ) VALUES (
      'active',
      NULLIF(p_display_label, ''),
      p_metadata,
      v_now,
      v_now
    )
    RETURNING id INTO v_principal_id;

    INSERT INTO identity_credentials (
      principal_id,
      provider,
      provider_environment,
      credential_kind,
      subject_digest,
      status,
      login_enabled,
      verified_at,
      last_authenticated_at,
      metadata,
      created_at,
      updated_at
    ) VALUES (
      v_principal_id,
      p_provider,
      'production',
      'federated',
      v_active_subject_digest,
      'active',
      TRUE,
      v_now,
      v_now,
      p_metadata,
      v_now,
      v_now
    )
    RETURNING id INTO v_credential_id;

    INSERT INTO identity_organization_memberships (
      organization_id,
      principal_id,
      role,
      status,
      activated_at,
      metadata,
      created_at,
      updated_at
    ) VALUES (
      p_organization_id,
      v_principal_id,
      'member',
      'active',
      v_now,
      '{}'::JSONB,
      v_now,
      v_now
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
      metadata,
      created_at,
      updated_at
    ) VALUES (
      p_organization_id,
      p_project_id,
      v_principal_id,
      v_organization_membership_id,
      'member',
      'active',
      v_now,
      '{}'::JSONB,
      v_now,
      v_now
    );

    v_created := TRUE;
  END IF;

  IF v_active_email_digest IS NOT NULL THEN
    FOR v_lock_digest IN
      SELECT DISTINCT email_candidate.digest
        FROM unnest(p_email_digests) AS email_candidate(digest)
       ORDER BY email_candidate.digest
    LOOP
      PERFORM pg_advisory_xact_lock(8102, hashtext(v_lock_digest));
    END LOOP;

    SELECT account_email.principal_id
      INTO v_email_owner
      FROM identity_account_emails AS account_email
     WHERE account_email.normalized_email_digest = ANY(p_email_digests)
     ORDER BY array_position(
       p_email_digests,
       account_email.normalized_email_digest
     )
     LIMIT 1
     FOR UPDATE;
    IF FOUND AND v_email_owner <> v_principal_id THEN
      RAISE EXCEPTION 'canonical_email_conflict'
        USING ERRCODE = '23505';
    END IF;

    SELECT account_email.normalized_email_digest
      INTO v_existing_email_digest
      FROM identity_account_emails AS account_email
     WHERE account_email.principal_id = v_principal_id
     FOR UPDATE;
    IF FOUND
       AND v_existing_email_digest <> ALL(p_email_digests) THEN
      RAISE EXCEPTION 'canonical_email_conflict'
        USING ERRCODE = '23505';
    END IF;

    INSERT INTO identity_account_emails (
      principal_id,
      normalized_email_digest,
      source_provider,
      verified_at,
      created_at,
      updated_at
    ) VALUES (
      v_principal_id,
      v_active_email_digest,
      p_provider,
      v_now,
      v_now,
      v_now
    )
    ON CONFLICT ON CONSTRAINT identity_account_emails_pkey DO UPDATE
      SET normalized_email_digest = EXCLUDED.normalized_email_digest,
          source_provider = EXCLUDED.source_provider,
          verified_at = EXCLUDED.verified_at,
          updated_at = EXCLUDED.updated_at;
  END IF;

  INSERT INTO identity_account_security (
    principal_id,
    two_factor_status,
    two_factor_recommended,
    updated_at
  ) VALUES (
    v_principal_id,
    'disabled',
    TRUE,
    v_now
  )
  ON CONFLICT ON CONSTRAINT identity_account_security_pkey DO NOTHING;

  SELECT token_ref_row.*
    INTO token_ref
    FROM oauth_token_opaque_refs AS token_ref_row
   WHERE token_ref_row.opaque_ref_digest = p_opaque_ref_digest
   FOR UPDATE;
  IF FOUND THEN
    RAISE EXCEPTION 'oauth_opaque_reference_conflict'
      USING ERRCODE = '23505';
  END IF;

  INSERT INTO oauth_token_opaque_refs (
    organization_id,
    project_id,
    provider,
    binding_digest,
    opaque_ref,
    opaque_ref_digest,
    status
  ) VALUES (
    p_organization_id,
    p_project_id,
    p_provider,
    p_binding_digest,
    p_opaque_ref,
    p_opaque_ref_digest,
    'active'
  )
  RETURNING id INTO v_token_ref_id;

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
    RAISE EXCEPTION 'oauth first-login session is unavailable'
      USING ERRCODE = '40001';
  END IF;

  PERFORM 1
    FROM oauth_account_connections AS connection_row
   WHERE connection_row.organization_id = p_organization_id
     AND connection_row.project_id = p_project_id
     AND connection_row.provider = p_provider
     AND (
       connection_row.credential_id = v_credential_id
       OR connection_row.provider_subject_digest = ANY(p_subject_digests)
     )
   ORDER BY connection_row.id
   FOR UPDATE;

  SELECT count(*)
    INTO v_connection_match_count
    FROM oauth_account_connections AS connection_row
   WHERE connection_row.organization_id = p_organization_id
     AND connection_row.project_id = p_project_id
     AND connection_row.provider = p_provider
     AND (
       connection_row.credential_id = v_credential_id
       OR connection_row.provider_subject_digest = ANY(p_subject_digests)
     );
  IF v_connection_match_count > 1 THEN
    RAISE EXCEPTION 'oauth subject connection candidates are ambiguous'
      USING ERRCODE = '23505';
  END IF;

  SELECT connection_row.*
    INTO connection
    FROM oauth_account_connections AS connection_row
   WHERE connection_row.organization_id = p_organization_id
     AND connection_row.project_id = p_project_id
     AND connection_row.provider = p_provider
     AND (
       connection_row.credential_id = v_credential_id
       OR connection_row.provider_subject_digest = ANY(p_subject_digests)
     )
   ORDER BY connection_row.id
   LIMIT 1
   FOR UPDATE;
  IF FOUND AND (
    connection.principal_id <> v_principal_id
    OR connection.credential_id <> v_credential_id
    OR connection.provider_subject_digest <> ALL(p_subject_digests)
    OR connection.status NOT IN ('active', 'reauthorization_required')
  ) THEN
    RAISE EXCEPTION 'oauth subject connection conflicts with canonical account'
      USING ERRCODE = '23505';
  END IF;

  IF FOUND THEN
    SELECT token_ref_row.*
      INTO previous_token_ref
      FROM oauth_token_opaque_refs AS token_ref_row
     WHERE token_ref_row.organization_id = p_organization_id
       AND token_ref_row.project_id = p_project_id
       AND token_ref_row.id = connection.token_ref_id
     FOR UPDATE;
    IF NOT FOUND OR previous_token_ref.provider <> p_provider THEN
      RAISE EXCEPTION 'oauth canonical token reference is unavailable'
        USING ERRCODE = '42501';
    END IF;

    UPDATE oauth_token_opaque_refs AS token_ref_row
       SET status = 'revocation_pending',
           revoked_at = NULL
     WHERE token_ref_row.id = previous_token_ref.id;

    INSERT INTO oauth_revocation_outbox (
      organization_id,
      project_id,
      provider,
      connection_id,
      token_ref_id,
      operation_kind,
      reason_code,
      status
    ) VALUES (
      p_organization_id,
      p_project_id,
      p_provider,
      connection.id,
      previous_token_ref.id,
      'provider_revoke_and_cleanup',
      'first_login_reauthenticated',
      'pending'
    )
    ON CONFLICT ON CONSTRAINT oauth_revocation_outbox_token_key DO NOTHING;

    UPDATE oauth_account_connections AS connection_row
       SET account_id = v_active_subject_digest,
           session_id = v_session_id::TEXT,
           user_id = v_principal_id::TEXT,
           binding_digest = p_binding_digest,
           provider_subject_digest = v_active_subject_digest,
           email_digest = v_active_email_digest,
           email_present = v_active_email_digest IS NOT NULL,
           token_ref_id = v_token_ref_id,
           status = 'active',
           disconnected_at = NULL,
           metadata = connection_row.metadata || p_metadata,
           updated_at = v_now
     WHERE connection_row.id = connection.id
    RETURNING connection_row.id INTO v_connection_id;
  ELSE
    INSERT INTO oauth_account_connections (
      organization_id,
      project_id,
      principal_id,
      credential_id,
      provider,
      account_id,
      session_id,
      user_id,
      binding_digest,
      provider_subject_digest,
      provider_login,
      email_digest,
      email_present,
      token_ref_id,
      status,
      metadata,
      connected_at,
      updated_at
    ) VALUES (
      p_organization_id,
      p_project_id,
      v_principal_id,
      v_credential_id,
      p_provider,
      v_active_subject_digest,
      v_session_id::TEXT,
      v_principal_id::TEXT,
      p_binding_digest,
      v_active_subject_digest,
      '[redacted]',
      v_active_email_digest,
      v_active_email_digest IS NOT NULL,
      v_token_ref_id,
      'active',
      p_metadata,
      v_now,
      v_now
    )
    RETURNING id INTO v_connection_id;
  END IF;

  PERFORM a1_identity_write_event(
    v_principal_id,
    p_organization_id,
    p_project_id,
    v_principal_id,
    'identity.oauth.first_login.completed',
    'oauth_account_connection',
    v_connection_id,
    p_request_digest,
    jsonb_build_object(
      'provider', p_provider,
      'credential_id', v_credential_id,
      'connection_id', v_connection_id,
      'token_ref_id', v_token_ref_id,
      'account_created', v_created,
      'assurance_level', 'aal1'
    )
  );

  UPDATE oauth_first_login_operations AS operation_row
     SET principal_id = v_principal_id,
         credential_id = v_credential_id,
         connection_id = v_connection_id,
         token_ref_id = v_token_ref_id,
         session_id = v_session_id,
         account_created = v_created,
         status = 'completed',
         completed_at = v_now
   WHERE operation_row.id = operation.id;

  RETURN QUERY SELECT
    v_session_id,
    v_principal_id,
    v_credential_id,
    v_connection_id,
    v_token_ref_id,
    v_created,
    session_row.organization_id,
    session_row.project_id,
    p_provider,
    session_row.expires_at,
    session_row.refresh_expires_at,
    v_now
  FROM identity_sessions AS session_row
  WHERE session_row.id = v_session_id
    AND session_row.principal_id = v_principal_id
    AND session_row.credential_id = v_credential_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'oauth first-login session relation is unavailable'
      USING ERRCODE = '40001';
  END IF;
END;
$$;

-- Scalar compatibility wrapper retained for already-deployed callers. New
-- production coordinators use the array authority above so active and retained
-- lookup-key digests can resolve and upgrade one canonical credential.
CREATE OR REPLACE FUNCTION a1_complete_oauth_first_login_with_refresh(
  p_organization_id UUID,
  p_project_id UUID,
  p_provider TEXT,
  p_subject_digest TEXT,
  p_email_digest TEXT,
  p_opaque_ref TEXT,
  p_opaque_ref_digest TEXT,
  p_binding_digest TEXT,
  p_session_digest TEXT,
  p_refresh_digest TEXT,
  p_rotation_family_digest TEXT,
  p_access_expires_at TIMESTAMPTZ,
  p_refresh_expires_at TIMESTAMPTZ,
  p_idempotency_digest TEXT,
  p_request_digest TEXT,
  p_display_label TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE (
  session_id UUID,
  principal_id UUID,
  credential_id UUID,
  connection_id UUID,
  token_ref_id UUID,
  created BOOLEAN,
  organization_id UUID,
  project_id UUID,
  provider_name TEXT,
  access_expires_at TIMESTAMPTZ,
  refresh_expires_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
  SELECT completed.*
    FROM a1_complete_oauth_first_login_with_refresh(
      p_organization_id,
      p_project_id,
      p_provider,
      ARRAY[p_subject_digest]::TEXT[],
      CASE
        WHEN p_email_digest IS NULL THEN ARRAY[]::TEXT[]
        ELSE ARRAY[p_email_digest]::TEXT[]
      END,
      p_opaque_ref,
      p_opaque_ref_digest,
      p_binding_digest,
      p_session_digest,
      p_refresh_digest,
      p_rotation_family_digest,
      p_access_expires_at,
      p_refresh_expires_at,
      p_idempotency_digest,
      p_request_digest,
      p_display_label,
      p_metadata
    ) AS completed
$$;

ALTER TABLE oauth_first_login_operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_first_login_operations FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS oauth_first_login_operations_tenant_isolation
  ON oauth_first_login_operations;
CREATE POLICY oauth_first_login_operations_tenant_isolation
  ON oauth_first_login_operations
  USING (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
  )
  WITH CHECK (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
  );

REVOKE ALL ON TABLE oauth_first_login_operations FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_complete_oauth_first_login_with_refresh(
  UUID,UUID,TEXT,TEXT[],TEXT[],TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,
  TIMESTAMPTZ,TIMESTAMPTZ,TEXT,TEXT,TEXT,JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_complete_oauth_first_login_with_refresh(
  UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,
  TIMESTAMPTZ,TIMESTAMPTZ,TEXT,TEXT,TEXT,JSONB
) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a1_runtime') THEN
    GRANT EXECUTE ON FUNCTION a1_complete_oauth_first_login_with_refresh(
      UUID,UUID,TEXT,TEXT[],TEXT[],TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,
      TIMESTAMPTZ,TIMESTAMPTZ,TEXT,TEXT,TEXT,JSONB
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_complete_oauth_first_login_with_refresh(
      UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,
      TIMESTAMPTZ,TIMESTAMPTZ,TEXT,TEXT,TEXT,JSONB
    ) TO a1_runtime;
  END IF;
END
$$;

COMMIT;
