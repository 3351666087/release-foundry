-- A1 atomic OAuth-to-canonical-identity coordinator and durable revoke outbox.
-- Only irreversible digests and opaque external-secret references cross this boundary.

BEGIN;

ALTER TABLE oauth_account_connections
  ADD COLUMN IF NOT EXISTS principal_id UUID,
  ADD COLUMN IF NOT EXISTS credential_id UUID;

ALTER TABLE oauth_account_connections
  DROP CONSTRAINT IF EXISTS oauth_account_connections_identity_pair_check;
ALTER TABLE oauth_account_connections
  ADD CONSTRAINT oauth_account_connections_identity_pair_check CHECK (
    (principal_id IS NULL AND credential_id IS NULL)
    OR (principal_id IS NOT NULL AND credential_id IS NOT NULL)
  );

ALTER TABLE oauth_account_connections
  DROP CONSTRAINT IF EXISTS oauth_account_connections_credential_scope_fk;
ALTER TABLE oauth_account_connections
  ADD CONSTRAINT oauth_account_connections_credential_scope_fk
  FOREIGN KEY (principal_id, credential_id)
  REFERENCES identity_credentials(principal_id, id) ON DELETE RESTRICT;

CREATE UNIQUE INDEX IF NOT EXISTS oauth_account_connections_credential_key
  ON oauth_account_connections(
    organization_id, project_id, provider, credential_id
  )
  WHERE credential_id IS NOT NULL;

ALTER TABLE oauth_account_connections
  DROP CONSTRAINT IF EXISTS oauth_account_connections_status_check;
ALTER TABLE oauth_account_connections
  ADD CONSTRAINT oauth_account_connections_status_check CHECK (
    status IN (
      'active', 'reauthorization_required',
      'revocation_pending', 'disconnected'
    )
  );

ALTER TABLE oauth_account_connections
  DROP CONSTRAINT IF EXISTS oauth_account_connections_status_time_check;
ALTER TABLE oauth_account_connections
  ADD CONSTRAINT oauth_account_connections_status_time_check CHECK (
    (status IN ('revocation_pending', 'disconnected')
      AND disconnected_at IS NOT NULL)
    OR (status IN ('active', 'reauthorization_required')
      AND disconnected_at IS NULL)
  );

ALTER TABLE oauth_revocation_outbox
  ADD COLUMN IF NOT EXISTS operation_kind TEXT NOT NULL
    DEFAULT 'provider_revoke_and_cleanup';
ALTER TABLE oauth_revocation_outbox
  DROP CONSTRAINT IF EXISTS oauth_revocation_outbox_operation_kind_check;
ALTER TABLE oauth_revocation_outbox
  ADD CONSTRAINT oauth_revocation_outbox_operation_kind_check CHECK (
    operation_kind IN ('provider_revoke_and_cleanup')
  );
ALTER TABLE oauth_revocation_outbox
  DROP CONSTRAINT IF EXISTS oauth_revocation_outbox_scope_id_key;
ALTER TABLE oauth_revocation_outbox
  ADD CONSTRAINT oauth_revocation_outbox_scope_id_key
  UNIQUE (organization_id, project_id, id);

CREATE TABLE IF NOT EXISTS oauth_identity_operations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  principal_id UUID NOT NULL,
  operation_kind TEXT NOT NULL
    CHECK (operation_kind IN ('callback', 'disconnect')),
  idempotency_digest TEXT NOT NULL
    CHECK (a1_identity_digest_valid(idempotency_digest)),
  request_digest TEXT NOT NULL
    CHECK (a1_identity_digest_valid(request_digest)),
  status TEXT NOT NULL DEFAULT 'processing'
    CHECK (status IN ('processing', 'completed')),
  credential_id UUID,
  connection_id UUID,
  token_ref_id UUID,
  outbox_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  completed_at TIMESTAMPTZ,
  CONSTRAINT oauth_identity_operations_scope_id_key
    UNIQUE (organization_id, project_id, id),
  CONSTRAINT oauth_identity_operations_idempotency_key
    UNIQUE (
      organization_id, project_id, operation_kind, idempotency_digest
    ),
  CONSTRAINT oauth_identity_operations_project_scope_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT oauth_identity_operations_principal_fk
    FOREIGN KEY (principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT oauth_identity_operations_credential_scope_fk
    FOREIGN KEY (principal_id, credential_id)
    REFERENCES identity_credentials(principal_id, id) ON DELETE RESTRICT,
  CONSTRAINT oauth_identity_operations_connection_scope_fk
    FOREIGN KEY (organization_id, project_id, connection_id)
    REFERENCES oauth_account_connections(
      organization_id, project_id, id
    ) ON DELETE RESTRICT,
  CONSTRAINT oauth_identity_operations_token_scope_fk
    FOREIGN KEY (organization_id, project_id, token_ref_id)
    REFERENCES oauth_token_opaque_refs(
      organization_id, project_id, id
    ) ON DELETE RESTRICT,
  CONSTRAINT oauth_identity_operations_outbox_scope_fk
    FOREIGN KEY (organization_id, project_id, outbox_id)
    REFERENCES oauth_revocation_outbox(
      organization_id, project_id, id
    ) ON DELETE RESTRICT,
  CONSTRAINT oauth_identity_operations_completion_check CHECK (
    (status = 'processing' AND completed_at IS NULL)
    OR (
      status = 'completed'
      AND completed_at IS NOT NULL
      AND credential_id IS NOT NULL
      AND connection_id IS NOT NULL
      AND token_ref_id IS NOT NULL
    )
  ),
  CONSTRAINT oauth_identity_operations_disconnect_outbox_check CHECK (
    operation_kind <> 'disconnect'
    OR status <> 'completed'
    OR outbox_id IS NOT NULL
  )
);

CREATE INDEX IF NOT EXISTS oauth_identity_operations_principal_created_idx
  ON oauth_identity_operations(
    organization_id, project_id, principal_id, created_at DESC
  );

CREATE OR REPLACE FUNCTION a1_oauth_identity_assert_context(
  p_organization_id UUID,
  p_project_id UUID,
  p_principal_id UUID
)
RETURNS VOID
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  PERFORM a1_assert_role_nobypassrls(session_user);
  IF p_organization_id IS DISTINCT FROM a1_current_organization_id()
     OR p_project_id IS DISTINCT FROM a1_current_project_id()
     OR p_principal_id IS DISTINCT FROM a1_current_principal_id() THEN
    RAISE EXCEPTION 'oauth identity tenant, project, or principal context mismatch'
      USING ERRCODE = '42501';
  END IF;
  IF NOT EXISTS (
    SELECT 1
      FROM projects
     WHERE organization_id = p_organization_id
       AND id = p_project_id
       AND status = 'active'
  ) THEN
    RAISE EXCEPTION 'active oauth identity project not found'
      USING ERRCODE = '42501';
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION a1_complete_oauth_identity_callback(
  p_organization_id UUID,
  p_project_id UUID,
  p_principal_id UUID,
  p_provider TEXT,
  p_provider_environment TEXT,
  p_subject_digest TEXT,
  p_binding_digest TEXT,
  p_opaque_ref TEXT,
  p_opaque_ref_digest TEXT,
  p_account_id TEXT,
  p_runtime_session_id TEXT,
  p_email_digest TEXT,
  p_idempotency_digest TEXT,
  p_request_digest TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE (
  operation_id UUID,
  credential_id UUID,
  connection_id UUID,
  token_ref_id UUID,
  operation_status TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  operation oauth_identity_operations%ROWTYPE;
  principal identity_principals%ROWTYPE;
  credential identity_credentials%ROWTYPE;
  token_ref oauth_token_opaque_refs%ROWTYPE;
  connection oauth_account_connections%ROWTYPE;
  now_value TIMESTAMPTZ := clock_timestamp();
BEGIN
  PERFORM a1_oauth_identity_assert_context(
    p_organization_id, p_project_id, p_principal_id
  );
  IF NOT a1_identity_provider_valid(p_provider)
     OR p_provider_environment NOT IN ('development', 'sandbox', 'production')
     OR NOT a1_identity_digest_valid(p_subject_digest)
     OR NOT a1_identity_digest_valid(p_binding_digest)
     OR NOT a1_oauth_reference_only(p_opaque_ref)
     OR NOT a1_identity_digest_valid(p_opaque_ref_digest)
     OR (p_email_digest IS NOT NULL
       AND NOT a1_identity_digest_valid(p_email_digest))
     OR NOT a1_identity_digest_valid(p_idempotency_digest)
     OR NOT a1_identity_digest_valid(p_request_digest)
     OR btrim(COALESCE(p_account_id, '')) = ''
     OR btrim(COALESCE(p_runtime_session_id, '')) = ''
     OR NOT a1_identity_public_metadata(p_metadata) THEN
    RAISE EXCEPTION 'oauth identity callback input rejected'
      USING ERRCODE = '22023';
  END IF;

  INSERT INTO oauth_identity_operations (
    organization_id, project_id, principal_id, operation_kind,
    idempotency_digest, request_digest
  ) VALUES (
    p_organization_id, p_project_id, p_principal_id, 'callback',
    p_idempotency_digest, p_request_digest
  )
  ON CONFLICT (
    organization_id, project_id, operation_kind, idempotency_digest
  ) DO NOTHING;

  SELECT *
    INTO operation
    FROM oauth_identity_operations
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND operation_kind = 'callback'
     AND idempotency_digest = p_idempotency_digest
   FOR UPDATE;
  IF operation.request_digest <> p_request_digest
     OR operation.principal_id <> p_principal_id THEN
    RAISE EXCEPTION 'oauth identity idempotency request mismatch'
      USING ERRCODE = '22000';
  END IF;
  IF operation.status = 'completed' THEN
    RETURN QUERY SELECT
      operation.id, operation.credential_id, operation.connection_id,
      operation.token_ref_id, operation.status;
    RETURN;
  END IF;

  SELECT *
    INTO principal
    FROM identity_principals
   WHERE id = p_principal_id
   FOR UPDATE;
  IF NOT FOUND OR principal.status NOT IN ('pending', 'active') THEN
    RAISE EXCEPTION 'identity principal is not linkable'
      USING ERRCODE = '42501';
  END IF;

  SELECT *
    INTO credential
    FROM identity_credentials
   WHERE provider = p_provider
     AND provider_environment = p_provider_environment
     AND subject_digest = p_subject_digest
   FOR UPDATE;
  IF FOUND AND credential.principal_id <> p_principal_id THEN
    RAISE EXCEPTION 'oauth subject already belongs to another principal'
      USING ERRCODE = '23505';
  END IF;
  IF FOUND AND credential.status NOT IN ('pending', 'active') THEN
    RAISE EXCEPTION 'oauth identity credential is not reusable'
      USING ERRCODE = '42501';
  END IF;
  IF FOUND THEN
    UPDATE identity_credentials
       SET status = 'active',
           login_enabled = TRUE,
           verified_at = COALESCE(verified_at, now_value),
           last_authenticated_at = now_value,
           metadata = metadata || p_metadata,
           updated_at = now_value
     WHERE id = credential.id
    RETURNING * INTO credential;
  ELSE
    INSERT INTO identity_credentials (
      principal_id, provider, provider_environment, credential_kind,
      subject_digest, status, login_enabled, verified_at,
      last_authenticated_at, metadata
    ) VALUES (
      p_principal_id, p_provider, p_provider_environment, 'federated',
      p_subject_digest, 'active', TRUE, now_value, now_value, p_metadata
    )
    RETURNING * INTO credential;
  END IF;

  SELECT *
    INTO token_ref
    FROM oauth_token_opaque_refs
   WHERE opaque_ref_digest = p_opaque_ref_digest
   FOR UPDATE;
  IF FOUND AND (
    token_ref.organization_id <> p_organization_id
    OR token_ref.project_id <> p_project_id
    OR token_ref.provider <> p_provider
    OR token_ref.binding_digest <> p_binding_digest
  ) THEN
    RAISE EXCEPTION 'oauth opaque reference is already bound elsewhere'
      USING ERRCODE = '23505';
  END IF;
  IF FOUND THEN
    UPDATE oauth_token_opaque_refs
       SET opaque_ref = p_opaque_ref,
           status = 'active',
           expires_at = NULL,
           superseded_at = NULL,
           revoked_at = NULL
     WHERE id = token_ref.id
    RETURNING * INTO token_ref;
  ELSE
    INSERT INTO oauth_token_opaque_refs (
      organization_id, project_id, provider, binding_digest,
      opaque_ref, opaque_ref_digest, status
    ) VALUES (
      p_organization_id, p_project_id, p_provider, p_binding_digest,
      p_opaque_ref, p_opaque_ref_digest, 'active'
    )
    RETURNING * INTO token_ref;
  END IF;

  SELECT *
    INTO connection
    FROM oauth_account_connections
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND provider = p_provider
     AND account_id = p_account_id
   FOR UPDATE;
  IF FOUND AND (
    connection.provider_subject_digest <> p_subject_digest
    OR (
      connection.credential_id IS NOT NULL
      AND connection.credential_id <> credential.id
    )
  ) THEN
    RAISE EXCEPTION 'oauth account binding conflicts with canonical credential'
      USING ERRCODE = '23505';
  END IF;
  IF FOUND THEN
    UPDATE oauth_account_connections
       SET principal_id = p_principal_id,
           credential_id = credential.id,
           session_id = p_runtime_session_id,
           user_id = p_principal_id::TEXT,
           binding_digest = p_binding_digest,
           email_digest = p_email_digest,
           email_present = p_email_digest IS NOT NULL,
           token_ref_id = token_ref.id,
           status = 'active',
           disconnected_at = NULL,
           metadata = metadata || p_metadata,
           updated_at = now_value
     WHERE id = connection.id
    RETURNING * INTO connection;
  ELSE
    INSERT INTO oauth_account_connections (
      organization_id, project_id, principal_id, credential_id,
      provider, account_id, session_id, user_id, binding_digest,
      provider_subject_digest, provider_login, email_digest,
      email_present, token_ref_id, status, metadata
    ) VALUES (
      p_organization_id, p_project_id, p_principal_id, credential.id,
      p_provider, p_account_id, p_runtime_session_id, p_principal_id::TEXT,
      p_binding_digest, p_subject_digest, '[redacted]', p_email_digest,
      p_email_digest IS NOT NULL, token_ref.id, 'active', p_metadata
    )
    RETURNING * INTO connection;
  END IF;

  IF principal.status = 'pending' THEN
    UPDATE identity_principals
       SET status = 'active', updated_at = now_value
     WHERE id = principal.id;
  END IF;
  PERFORM a1_identity_write_event(
    p_principal_id, p_organization_id, p_project_id, p_principal_id,
    'identity.oauth.callback_completed', 'oauth_account_connection',
    connection.id, p_request_digest,
    jsonb_build_object(
      'provider', p_provider,
      'provider_environment', p_provider_environment,
      'credential_id', credential.id,
      'token_ref_id', token_ref.id
    )
  );

  UPDATE oauth_identity_operations
     SET status = 'completed',
         credential_id = credential.id,
         connection_id = connection.id,
         token_ref_id = token_ref.id,
         completed_at = now_value
   WHERE id = operation.id
  RETURNING * INTO operation;

  RETURN QUERY SELECT
    operation.id, operation.credential_id, operation.connection_id,
    operation.token_ref_id, operation.status;
END;
$$;

CREATE OR REPLACE FUNCTION a1_disconnect_oauth_identity_credential(
  p_organization_id UUID,
  p_project_id UUID,
  p_principal_id UUID,
  p_credential_id UUID,
  p_connection_id UUID,
  p_reason_code TEXT,
  p_idempotency_digest TEXT,
  p_request_digest TEXT
)
RETURNS TABLE (
  operation_id UUID,
  credential_id UUID,
  connection_id UUID,
  token_ref_id UUID,
  outbox_id UUID,
  operation_status TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  operation oauth_identity_operations%ROWTYPE;
  credential identity_credentials%ROWTYPE;
  connection oauth_account_connections%ROWTYPE;
  token_ref oauth_token_opaque_refs%ROWTYPE;
  revoke_outbox oauth_revocation_outbox%ROWTYPE;
  active_login_count INTEGER;
  now_value TIMESTAMPTZ := clock_timestamp();
BEGIN
  PERFORM a1_oauth_identity_assert_context(
    p_organization_id, p_project_id, p_principal_id
  );
  IF btrim(COALESCE(p_reason_code, '')) = ''
     OR NOT a1_identity_digest_valid(p_idempotency_digest)
     OR NOT a1_identity_digest_valid(p_request_digest) THEN
    RAISE EXCEPTION 'oauth identity disconnect input rejected'
      USING ERRCODE = '22023';
  END IF;

  INSERT INTO oauth_identity_operations (
    organization_id, project_id, principal_id, operation_kind,
    idempotency_digest, request_digest
  ) VALUES (
    p_organization_id, p_project_id, p_principal_id, 'disconnect',
    p_idempotency_digest, p_request_digest
  )
  ON CONFLICT (
    organization_id, project_id, operation_kind, idempotency_digest
  ) DO NOTHING;

  SELECT *
    INTO operation
    FROM oauth_identity_operations
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND operation_kind = 'disconnect'
     AND idempotency_digest = p_idempotency_digest
   FOR UPDATE;
  IF operation.request_digest <> p_request_digest
     OR operation.principal_id <> p_principal_id THEN
    RAISE EXCEPTION 'oauth identity idempotency request mismatch'
      USING ERRCODE = '22000';
  END IF;
  IF operation.status = 'completed' THEN
    RETURN QUERY SELECT
      operation.id, operation.credential_id, operation.connection_id,
      operation.token_ref_id, operation.outbox_id, operation.status;
    RETURN;
  END IF;

  PERFORM 1
    FROM identity_principals
   WHERE id = p_principal_id
     AND status IN ('active', 'locked')
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity principal is not disconnectable'
      USING ERRCODE = '42501';
  END IF;

  SELECT *
    INTO credential
    FROM identity_credentials
   WHERE principal_id = p_principal_id
     AND id = p_credential_id
   FOR UPDATE;
  IF NOT FOUND OR credential.status <> 'active' THEN
    RAISE EXCEPTION 'active identity credential not found'
      USING ERRCODE = 'P0002';
  END IF;

  SELECT *
    INTO connection
    FROM oauth_account_connections
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = p_connection_id
   FOR UPDATE;
  IF NOT FOUND
     OR connection.principal_id <> p_principal_id
     OR connection.credential_id <> p_credential_id
     OR connection.provider <> credential.provider
     OR connection.provider_subject_digest <> credential.subject_digest
     OR connection.status NOT IN ('active', 'reauthorization_required') THEN
    RAISE EXCEPTION 'canonical oauth connection not found'
      USING ERRCODE = 'P0002';
  END IF;

  SELECT *
    INTO token_ref
    FROM oauth_token_opaque_refs
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND id = connection.token_ref_id
   FOR UPDATE;
  IF NOT FOUND OR token_ref.provider <> credential.provider THEN
    RAISE EXCEPTION 'canonical oauth token reference not found'
      USING ERRCODE = 'P0002';
  END IF;

  SELECT count(*)
    INTO active_login_count
    FROM identity_credentials
   WHERE principal_id = p_principal_id
     AND status = 'active'
     AND login_enabled;
  IF credential.login_enabled AND active_login_count <= 1 THEN
    RAISE EXCEPTION 'cannot disconnect the last active login credential'
      USING ERRCODE = '23514';
  END IF;

  UPDATE identity_credentials
     SET status = 'revoked',
         login_enabled = FALSE,
         revoked_at = now_value,
         secret_ref = NULL,
         updated_at = now_value
   WHERE id = credential.id
  RETURNING * INTO credential;
  UPDATE identity_sessions AS session_row
     SET status = 'revoked',
         revoked_at = now_value,
         revoke_reason_code = 'credential_disconnected'
   WHERE session_row.principal_id = p_principal_id
     AND session_row.credential_id = p_credential_id
     AND session_row.status = 'active';
  UPDATE oauth_account_connections
     SET status = 'revocation_pending',
         disconnected_at = now_value,
         updated_at = now_value
   WHERE id = connection.id
  RETURNING * INTO connection;
  UPDATE oauth_token_opaque_refs
     SET status = 'revocation_pending',
         revoked_at = NULL
   WHERE id = token_ref.id
  RETURNING * INTO token_ref;

  INSERT INTO oauth_revocation_outbox (
    organization_id, project_id, provider, connection_id, token_ref_id,
    operation_kind, reason_code, status
  ) VALUES (
    p_organization_id, p_project_id, connection.provider,
    connection.id, token_ref.id, 'provider_revoke_and_cleanup',
    p_reason_code, 'pending'
  )
  ON CONFLICT ON CONSTRAINT oauth_revocation_outbox_token_key DO UPDATE
    SET updated_at = oauth_revocation_outbox.updated_at
  RETURNING * INTO revoke_outbox;

  PERFORM a1_identity_write_event(
    p_principal_id, p_organization_id, p_project_id, p_principal_id,
    'identity.oauth.revocation_pending', 'oauth_account_connection',
    connection.id, p_request_digest,
    jsonb_build_object(
      'provider', connection.provider,
      'credential_id', credential.id,
      'token_ref_id', token_ref.id,
      'revocation_outbox_id', revoke_outbox.id,
      'reason_code', p_reason_code
    )
  );

  UPDATE oauth_identity_operations
     SET status = 'completed',
         credential_id = credential.id,
         connection_id = connection.id,
         token_ref_id = token_ref.id,
         outbox_id = revoke_outbox.id,
         completed_at = now_value
   WHERE id = operation.id
  RETURNING * INTO operation;

  RETURN QUERY SELECT
    operation.id, operation.credential_id, operation.connection_id,
    operation.token_ref_id, operation.outbox_id, operation.status;
END;
$$;

ALTER TABLE oauth_identity_operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_identity_operations FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS oauth_identity_operations_tenant_isolation
  ON oauth_identity_operations;
CREATE POLICY oauth_identity_operations_tenant_isolation
  ON oauth_identity_operations
  USING (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
    AND principal_id = a1_current_principal_id()
  )
  WITH CHECK (
    organization_id = a1_current_organization_id()
    AND project_id = a1_current_project_id()
    AND principal_id = a1_current_principal_id()
  );

REVOKE ALL ON FUNCTION a1_oauth_identity_assert_context(
  UUID, UUID, UUID
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_complete_oauth_identity_callback(
  UUID, UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TEXT, TEXT, TEXT, TEXT, TEXT, JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_disconnect_oauth_identity_credential(
  UUID, UUID, UUID, UUID, UUID, TEXT, TEXT, TEXT
) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a1_runtime') THEN
    GRANT SELECT ON oauth_identity_operations TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_oauth_identity_assert_context(
      UUID, UUID, UUID
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_complete_oauth_identity_callback(
      UUID, UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
      TEXT, TEXT, TEXT, TEXT, TEXT, JSONB
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_disconnect_oauth_identity_credential(
      UUID, UUID, UUID, UUID, UUID, TEXT, TEXT, TEXT
    ) TO a1_runtime;
  END IF;
END;
$$;

COMMIT;
