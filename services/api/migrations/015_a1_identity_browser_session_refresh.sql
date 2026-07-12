-- Browser-session refresh bootstrap over digest-only PostgreSQL state.
BEGIN;

CREATE OR REPLACE FUNCTION a1_rotate_identity_session_refresh_from_digest(
  p_project_id UUID,
  p_principal_id UUID,
  p_refresh_digest TEXT,
  p_new_session_digest TEXT,
  p_new_refresh_digest TEXT,
  p_requested_access_expires_at TIMESTAMPTZ,
  p_idempotency_digest TEXT,
  p_request_digest TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE (
  session_id UUID,
  organization_id UUID,
  project_id UUID,
  principal_id UUID,
  rotation_generation BIGINT,
  outcome_code TEXT,
  affected_count INTEGER,
  access_expires_at TIMESTAMPTZ,
  refresh_expires_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  current_session identity_sessions%ROWTYPE;
  rotation_result RECORD;
  v_now TIMESTAMPTZ := clock_timestamp();
  v_access_expires_at TIMESTAMPTZ;
  v_returned_access_expires_at TIMESTAMPTZ;
  v_returned_refresh_expires_at TIMESTAMPTZ;
BEGIN
  PERFORM a1_assert_role_nobypassrls(session_user);
  IF p_project_id IS NULL
     OR p_principal_id IS NULL
     OR NOT a1_identity_digest_valid(p_refresh_digest)
     OR NOT a1_identity_digest_valid(p_new_session_digest)
     OR NOT a1_identity_digest_valid(p_new_refresh_digest)
     OR NOT a1_identity_digest_valid(p_idempotency_digest)
     OR NOT a1_identity_digest_valid(p_request_digest)
     OR p_refresh_digest = p_new_refresh_digest
     OR p_new_session_digest = p_new_refresh_digest
     OR p_requested_access_expires_at IS NULL
     OR NOT a1_identity_public_metadata(p_metadata) THEN
    RAISE EXCEPTION 'identity refresh is unavailable'
      USING ERRCODE = '42501';
  END IF;

  SELECT session_row.*
    INTO current_session
    FROM identity_sessions AS session_row
   WHERE session_row.refresh_digest = p_refresh_digest;
  IF NOT FOUND
     OR current_session.project_id <> p_project_id
     OR current_session.principal_id <> p_principal_id
     OR current_session.organization_id IS NULL
     OR current_session.refresh_expires_at IS NULL THEN
    RAISE EXCEPTION 'identity refresh is unavailable'
      USING ERRCODE = '42501';
  END IF;

  -- Match the core rotation lock order. A concurrent retry that waits here
  -- receives a fresh statement snapshot before re-reading the session row,
  -- so it can deterministically replay the committed lifecycle operation.
  PERFORM 1
    FROM identity_principals AS principal
   WHERE principal.id = current_session.principal_id
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity refresh is unavailable'
      USING ERRCODE = '42501';
  END IF;

  SELECT session_row.*
    INTO current_session
    FROM identity_sessions AS session_row
   WHERE session_row.refresh_digest = p_refresh_digest
   FOR UPDATE;
  IF NOT FOUND
     OR current_session.project_id <> p_project_id
     OR current_session.principal_id <> p_principal_id
     OR current_session.organization_id IS NULL
     OR current_session.refresh_expires_at IS NULL THEN
    RAISE EXCEPTION 'identity refresh is unavailable'
      USING ERRCODE = '42501';
  END IF;

  PERFORM set_config(
    'app.a1_organization_id', current_session.organization_id::TEXT, TRUE
  );
  PERFORM set_config(
    'app.a1_project_id', current_session.project_id::TEXT, TRUE
  );
  PERFORM set_config(
    'app.a1_principal_id', current_session.principal_id::TEXT, TRUE
  );

  v_access_expires_at := LEAST(
    p_requested_access_expires_at,
    current_session.refresh_expires_at - INTERVAL '1 second'
  );
  IF v_access_expires_at <= v_now THEN
    RAISE EXCEPTION 'identity refresh is unavailable'
      USING ERRCODE = '42501';
  END IF;

  SELECT rotated.*
    INTO rotation_result
    FROM a1_rotate_identity_session_refresh(
      current_session.organization_id,
      current_session.project_id,
      current_session.principal_id,
      p_refresh_digest,
      current_session.rotation_generation,
      p_new_session_digest,
      p_new_refresh_digest,
      v_access_expires_at,
      current_session.refresh_expires_at,
      p_idempotency_digest,
      p_request_digest,
      p_metadata
    ) AS rotated;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity refresh is unavailable'
      USING ERRCODE = '42501';
  END IF;

  SELECT COALESCE(result_session.expires_at, v_access_expires_at),
         COALESCE(
           result_session.refresh_expires_at,
           current_session.refresh_expires_at
         )
    INTO v_returned_access_expires_at, v_returned_refresh_expires_at
    FROM (SELECT 1) AS singleton
    LEFT JOIN identity_sessions AS result_session
      ON result_session.id = rotation_result.session_id;

  RETURN QUERY SELECT
    rotation_result.session_id::UUID,
    current_session.organization_id,
    current_session.project_id,
    current_session.principal_id,
    rotation_result.rotation_generation::BIGINT,
    rotation_result.outcome_code::TEXT,
    rotation_result.affected_count::INTEGER,
    v_returned_access_expires_at,
    v_returned_refresh_expires_at;
END;
$$;

REVOKE ALL ON FUNCTION a1_rotate_identity_session_refresh_from_digest(
  UUID, UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, TEXT, JSONB
) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a1_runtime') THEN
    GRANT EXECUTE ON FUNCTION a1_rotate_identity_session_refresh_from_digest(
      UUID, UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, TEXT, JSONB
    ) TO a1_runtime;
  END IF;
END;
$$;

COMMIT;
