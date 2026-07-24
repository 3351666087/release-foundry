-- A1 restricted-role OAuth first-login runtime transaction entrypoint.
-- The runtime role may execute this narrowly scoped function but must not
-- receive direct privileges on oauth_runtime_transactions.
BEGIN;

CREATE OR REPLACE FUNCTION a1_create_oauth_runtime_transaction(
  p_organization_id UUID,
  p_project_id UUID,
  p_provider TEXT,
  p_state_digest TEXT,
  p_binding_digest TEXT,
  p_transaction_ref TEXT,
  p_created_at TIMESTAMPTZ,
  p_expires_at TIMESTAMPTZ
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
  PERFORM a1_assert_role_nobypassrls(session_user);

  IF p_organization_id IS NULL
     OR p_project_id IS NULL
     OR p_organization_id IS DISTINCT FROM a1_current_organization_id()
     OR p_project_id IS DISTINCT FROM a1_current_project_id() THEN
    RAISE EXCEPTION 'oauth runtime transaction scope mismatch'
      USING ERRCODE = '42501';
  END IF;
  IF p_provider IS NULL OR p_provider !~ '^[a-z][a-z0-9_-]{1,31}$' THEN
    RAISE EXCEPTION 'oauth provider is invalid'
      USING ERRCODE = '22023';
  END IF;
  IF p_state_digest IS NULL OR p_state_digest !~ '^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION 'oauth state digest must be sha256 hex'
      USING ERRCODE = '22023';
  END IF;
  IF p_binding_digest IS NULL OR p_binding_digest !~ '^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION 'oauth binding digest must be sha256 hex'
      USING ERRCODE = '22023';
  END IF;
  IF p_transaction_ref IS NULL
     OR NOT a1_oauth_reference_only(p_transaction_ref) THEN
    RAISE EXCEPTION 'oauth transaction reference must be opaque'
      USING ERRCODE = '22023';
  END IF;
  IF p_created_at IS NULL
     OR p_expires_at IS NULL
     OR p_expires_at <= p_created_at
     OR p_expires_at > p_created_at + INTERVAL '30 minutes' THEN
    RAISE EXCEPTION 'oauth runtime transaction lifetime is invalid'
      USING ERRCODE = '22023';
  END IF;

  INSERT INTO oauth_runtime_transactions (
    organization_id,
    project_id,
    provider,
    state_digest,
    binding_digest,
    transaction_ref,
    created_at,
    expires_at
  ) VALUES (
    p_organization_id,
    p_project_id,
    p_provider,
    p_state_digest,
    p_binding_digest,
    p_transaction_ref,
    p_created_at,
    p_expires_at
  );
  RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION a1_create_oauth_runtime_transaction(
  UUID, UUID, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ
) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'a1_runtime') THEN
    GRANT EXECUTE ON FUNCTION a1_create_oauth_runtime_transaction(
      UUID, UUID, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ
    ) TO a1_runtime;
  END IF;
END;
$$;

COMMIT;
