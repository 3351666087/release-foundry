-- Digest-only identity session refresh, revocation, and recovery lifecycle.
-- Raw access and refresh bearer values must be SHA-256 digested before they
-- cross this PostgreSQL boundary. Session-family mutations are serialized by
-- the principal row and fenced by a monotonically increasing generation.

BEGIN;

ALTER TABLE identity_sessions
  ADD COLUMN IF NOT EXISTS refresh_digest TEXT,
  ADD COLUMN IF NOT EXISTS refresh_expires_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS rotation_generation BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS rotated_from_session_id UUID,
  ADD COLUMN IF NOT EXISTS rotated_to_session_id UUID,
  ADD COLUMN IF NOT EXISTS rotation_idempotency_digest TEXT,
  ADD COLUMN IF NOT EXISTS rotation_request_digest TEXT;

ALTER TABLE identity_sessions
  DROP CONSTRAINT IF EXISTS identity_sessions_refresh_digest_check;
ALTER TABLE identity_sessions
  ADD CONSTRAINT identity_sessions_refresh_digest_check CHECK (
    refresh_digest IS NULL OR a1_identity_digest_valid(refresh_digest)
  );

ALTER TABLE identity_sessions
  DROP CONSTRAINT IF EXISTS identity_sessions_refresh_ttl_check;
ALTER TABLE identity_sessions
  ADD CONSTRAINT identity_sessions_refresh_ttl_check CHECK (
    (refresh_digest IS NULL AND refresh_expires_at IS NULL)
    OR (
      refresh_digest IS NOT NULL
      AND refresh_expires_at IS NOT NULL
      AND refresh_expires_at > expires_at
    )
  );

ALTER TABLE identity_sessions
  DROP CONSTRAINT IF EXISTS identity_sessions_rotation_generation_check;
ALTER TABLE identity_sessions
  ADD CONSTRAINT identity_sessions_rotation_generation_check CHECK (
    rotation_generation >= 0
  );

ALTER TABLE identity_sessions
  DROP CONSTRAINT IF EXISTS identity_sessions_rotation_idempotency_check;
ALTER TABLE identity_sessions
  ADD CONSTRAINT identity_sessions_rotation_idempotency_check CHECK (
    (rotation_idempotency_digest IS NULL
      AND rotation_request_digest IS NULL)
    OR (
      a1_identity_digest_valid(rotation_idempotency_digest)
      AND a1_identity_digest_valid(rotation_request_digest)
    )
  );

ALTER TABLE identity_sessions
  DROP CONSTRAINT IF EXISTS identity_sessions_rotation_lineage_check;
ALTER TABLE identity_sessions
  ADD CONSTRAINT identity_sessions_rotation_lineage_check CHECK (
    (rotation_generation = 0 OR rotated_from_session_id IS NOT NULL)
    AND (rotated_from_session_id IS NULL OR rotated_from_session_id <> id)
    AND (rotated_to_session_id IS NULL OR rotated_to_session_id <> id)
    AND (
      status <> 'rotated'
      OR (
        refresh_digest IS NOT NULL
        AND rotated_at IS NOT NULL
        AND rotated_to_session_id IS NOT NULL
        AND rotation_idempotency_digest IS NOT NULL
        AND rotation_request_digest IS NOT NULL
      )
    )
  );

-- Revoked members may retain rotated_at as durable family history.
ALTER TABLE identity_sessions
  DROP CONSTRAINT IF EXISTS identity_sessions_rotation_state_check;
ALTER TABLE identity_sessions
  ADD CONSTRAINT identity_sessions_rotation_state_check CHECK (
    (status = 'rotated' AND rotated_at IS NOT NULL)
    OR (status IN ('active', 'expired') AND rotated_at IS NULL)
    OR status = 'revoked'
  );

ALTER TABLE identity_sessions
  DROP CONSTRAINT IF EXISTS identity_sessions_rotated_from_fk;
ALTER TABLE identity_sessions
  ADD CONSTRAINT identity_sessions_rotated_from_fk
  FOREIGN KEY (rotated_from_session_id)
  REFERENCES identity_sessions(id) ON DELETE RESTRICT
  DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE identity_sessions
  DROP CONSTRAINT IF EXISTS identity_sessions_rotated_to_fk;
ALTER TABLE identity_sessions
  ADD CONSTRAINT identity_sessions_rotated_to_fk
  FOREIGN KEY (rotated_to_session_id)
  REFERENCES identity_sessions(id) ON DELETE RESTRICT
  DEFERRABLE INITIALLY DEFERRED;

CREATE UNIQUE INDEX IF NOT EXISTS identity_sessions_refresh_digest_key
  ON identity_sessions(refresh_digest)
  WHERE refresh_digest IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS identity_sessions_family_generation_key
  ON identity_sessions(rotation_family_digest, rotation_generation);

CREATE UNIQUE INDEX IF NOT EXISTS identity_sessions_family_active_key
  ON identity_sessions(rotation_family_digest)
  WHERE status = 'active';

CREATE INDEX IF NOT EXISTS identity_sessions_scope_account_status_idx
  ON identity_sessions(
    organization_id, project_id, principal_id, status, authenticated_at DESC
  );

CREATE TABLE IF NOT EXISTS identity_session_lifecycle_operations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  principal_id UUID NOT NULL,
  operation_kind TEXT NOT NULL CHECK (
    operation_kind IN (
      'issue', 'rotate', 'revoke_one', 'revoke_all',
      'recovery_invalidate'
    )
  ),
  idempotency_digest TEXT NOT NULL CHECK (
    a1_identity_digest_valid(idempotency_digest)
  ),
  request_digest TEXT NOT NULL CHECK (
    a1_identity_digest_valid(request_digest)
  ),
  actor_session_id UUID,
  target_session_id UUID,
  result_session_id UUID,
  outcome_code TEXT NOT NULL CHECK (
    outcome_code IN (
      'issued', 'rotated', 'refresh_reuse_detected', 'revoked',
      'already_revoked', 'revoked_all', 'recovery_invalidated'
    )
  ),
  affected_count INTEGER NOT NULL DEFAULT 0 CHECK (affected_count >= 0),
  completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT identity_session_lifecycle_operations_idempotency_key UNIQUE (
    organization_id, project_id, principal_id,
    operation_kind, idempotency_digest
  ),
  CONSTRAINT identity_session_lifecycle_operations_project_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT identity_session_lifecycle_operations_principal_fk
    FOREIGN KEY (principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT identity_session_lifecycle_operations_actor_fk
    FOREIGN KEY (actor_session_id)
    REFERENCES identity_sessions(id) ON DELETE RESTRICT,
  CONSTRAINT identity_session_lifecycle_operations_target_fk
    FOREIGN KEY (target_session_id)
    REFERENCES identity_sessions(id) ON DELETE RESTRICT,
  CONSTRAINT identity_session_lifecycle_operations_result_fk
    FOREIGN KEY (result_session_id)
    REFERENCES identity_sessions(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS identity_session_lifecycle_operations_scope_idx
  ON identity_session_lifecycle_operations(
    organization_id, project_id, principal_id, created_at DESC
  );

CREATE OR REPLACE FUNCTION a1_identity_session_assert_scope(
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

  IF p_organization_id IS NULL
     OR p_project_id IS NULL
     OR p_principal_id IS NULL
     OR p_organization_id IS DISTINCT FROM a1_current_organization_id()
     OR p_project_id IS DISTINCT FROM a1_current_project_id()
     OR p_principal_id IS DISTINCT FROM a1_current_principal_id() THEN
    RAISE EXCEPTION 'identity session scope is unavailable'
      USING ERRCODE = '42501';
  END IF;

  IF NOT EXISTS (
    SELECT 1
      FROM identity_principals AS principal
      JOIN identity_organization_memberships AS organization_membership
        ON organization_membership.principal_id = principal.id
       AND organization_membership.organization_id = p_organization_id
       AND organization_membership.status = 'active'
      JOIN identity_project_memberships AS project_membership
        ON project_membership.principal_id = principal.id
       AND project_membership.organization_id = p_organization_id
       AND project_membership.project_id = p_project_id
       AND project_membership.organization_membership_id =
            organization_membership.id
       AND project_membership.status = 'active'
      JOIN projects AS project
        ON project.organization_id = project_membership.organization_id
       AND project.id = project_membership.project_id
       AND project.status = 'active'
      JOIN organizations AS organization
        ON organization.id = project.organization_id
       AND organization.status = 'active'
     WHERE principal.id = p_principal_id
       AND principal.status = 'active'
  ) THEN
    RAISE EXCEPTION 'identity session scope is unavailable'
      USING ERRCODE = '42501';
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION a1_assert_recent_identity_authentication(
  p_organization_id UUID,
  p_project_id UUID,
  p_principal_id UUID,
  p_session_digest TEXT,
  p_max_age_seconds INTEGER,
  p_minimum_assurance_level TEXT
)
RETURNS UUID
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  recent_session_id UUID;
  minimum_rank INTEGER;
  v_now TIMESTAMPTZ := clock_timestamp();
BEGIN
  PERFORM a1_identity_session_assert_scope(
    p_organization_id, p_project_id, p_principal_id
  );

  minimum_rank := CASE p_minimum_assurance_level
    WHEN 'aal1' THEN 1
    WHEN 'aal2' THEN 2
    WHEN 'aal3' THEN 3
    ELSE 0
  END;
  IF NOT a1_identity_digest_valid(p_session_digest)
     OR p_max_age_seconds < 1
     OR p_max_age_seconds > 86400
     OR minimum_rank = 0 THEN
    RAISE EXCEPTION 'recent authentication request is invalid'
      USING ERRCODE = '22023';
  END IF;

  SELECT session_row.id
    INTO recent_session_id
    FROM identity_sessions AS session_row
    JOIN identity_credentials AS credential
      ON credential.principal_id = session_row.principal_id
     AND credential.id = session_row.credential_id
     AND credential.status = 'active'
     AND credential.login_enabled
   WHERE session_row.organization_id = p_organization_id
     AND session_row.project_id = p_project_id
     AND session_row.principal_id = p_principal_id
     AND session_row.session_digest = p_session_digest
     AND session_row.status = 'active'
     AND session_row.expires_at > v_now
     AND session_row.authenticated_at >=
           v_now - make_interval(secs => p_max_age_seconds)
     AND CASE session_row.assurance_level
           WHEN 'aal1' THEN 1
           WHEN 'aal2' THEN 2
           WHEN 'aal3' THEN 3
           ELSE 0
         END >= minimum_rank
   LIMIT 1;

  IF recent_session_id IS NULL THEN
    RAISE EXCEPTION 'recent_authentication_required'
      USING ERRCODE = '42501';
  END IF;
  RETURN recent_session_id;
END;
$$;

CREATE OR REPLACE FUNCTION a1_issue_identity_session_with_refresh(
  p_organization_id UUID,
  p_project_id UUID,
  p_principal_id UUID,
  p_credential_id UUID,
  p_session_digest TEXT,
  p_refresh_digest TEXT,
  p_rotation_family_digest TEXT,
  p_access_expires_at TIMESTAMPTZ,
  p_refresh_expires_at TIMESTAMPTZ,
  p_assurance_level TEXT,
  p_idempotency_digest TEXT,
  p_request_digest TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE (
  session_id UUID,
  rotation_generation BIGINT,
  outcome_code TEXT,
  affected_count INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  existing_operation identity_session_lifecycle_operations%ROWTYPE;
  credential identity_credentials%ROWTYPE;
  created_session_id UUID := gen_random_uuid();
  v_now TIMESTAMPTZ := clock_timestamp();
BEGIN
  PERFORM a1_identity_session_assert_scope(
    p_organization_id, p_project_id, p_principal_id
  );
  IF NOT a1_identity_digest_valid(p_session_digest)
     OR NOT a1_identity_digest_valid(p_refresh_digest)
     OR NOT a1_identity_digest_valid(p_rotation_family_digest)
     OR NOT a1_identity_digest_valid(p_idempotency_digest)
     OR NOT a1_identity_digest_valid(p_request_digest)
     OR p_session_digest = p_refresh_digest
     OR p_refresh_expires_at <= p_access_expires_at
     OR p_assurance_level NOT IN ('aal1', 'aal2', 'aal3')
     OR NOT a1_identity_public_metadata(p_metadata) THEN
    RAISE EXCEPTION 'identity session issuance is invalid'
      USING ERRCODE = '22023';
  END IF;

  PERFORM 1
    FROM identity_principals AS principal
   WHERE principal.id = p_principal_id
     AND principal.status = 'active'
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity session scope is unavailable'
      USING ERRCODE = '42501';
  END IF;

  SELECT operation.*
    INTO existing_operation
    FROM identity_session_lifecycle_operations AS operation
   WHERE operation.organization_id = p_organization_id
     AND operation.project_id = p_project_id
     AND operation.principal_id = p_principal_id
     AND operation.operation_kind = 'issue'
     AND operation.idempotency_digest = p_idempotency_digest
   FOR UPDATE;
  IF FOUND THEN
    IF existing_operation.request_digest <> p_request_digest THEN
      RAISE EXCEPTION 'idempotency_conflict'
        USING ERRCODE = '23505';
    END IF;
    RETURN QUERY
    SELECT session_row.id, session_row.rotation_generation,
           existing_operation.outcome_code,
           existing_operation.affected_count
      FROM identity_sessions AS session_row
     WHERE session_row.id = existing_operation.result_session_id;
    RETURN;
  END IF;

  IF p_access_expires_at <= v_now THEN
    RAISE EXCEPTION 'identity session issuance is invalid'
      USING ERRCODE = '22023';
  END IF;

  SELECT credential_row.*
    INTO credential
    FROM identity_credentials AS credential_row
   WHERE credential_row.principal_id = p_principal_id
     AND credential_row.id = p_credential_id
     AND credential_row.status = 'active'
     AND credential_row.login_enabled
   FOR KEY SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity session credential is unavailable'
      USING ERRCODE = '42501';
  END IF;

  IF EXISTS (
    SELECT 1
      FROM identity_sessions AS session_row
     WHERE session_row.rotation_family_digest = p_rotation_family_digest
  ) THEN
    RAISE EXCEPTION 'rotation_family_conflict'
      USING ERRCODE = '40001';
  END IF;

  INSERT INTO identity_sessions (
    id, principal_id, credential_id, organization_id, project_id,
    session_digest, refresh_digest, rotation_family_digest,
    rotation_generation, status, assurance_level,
    authenticated_at, expires_at, refresh_expires_at, metadata
  ) VALUES (
    created_session_id, p_principal_id, p_credential_id,
    p_organization_id, p_project_id, p_session_digest, p_refresh_digest,
    p_rotation_family_digest, 0, 'active', p_assurance_level,
    v_now, p_access_expires_at, p_refresh_expires_at, p_metadata
  );

  INSERT INTO identity_session_lifecycle_operations (
    organization_id, project_id, principal_id, operation_kind,
    idempotency_digest, request_digest, result_session_id,
    outcome_code, affected_count, completed_at
  ) VALUES (
    p_organization_id, p_project_id, p_principal_id, 'issue',
    p_idempotency_digest, p_request_digest, created_session_id,
    'issued', 1, v_now
  );

  PERFORM a1_identity_write_event(
    p_principal_id, p_organization_id, p_project_id, p_principal_id,
    'identity.session.issued_with_refresh', 'identity_session',
    created_session_id, p_request_digest,
    jsonb_build_object(
      'assurance_level', p_assurance_level,
      'credential_id', p_credential_id,
      'rotation_generation', 0
    )
  );

  RETURN QUERY SELECT created_session_id, 0::BIGINT, 'issued'::TEXT, 1;
END;
$$;

CREATE OR REPLACE FUNCTION a1_rotate_identity_session_refresh(
  p_organization_id UUID,
  p_project_id UUID,
  p_principal_id UUID,
  p_refresh_digest TEXT,
  p_expected_generation BIGINT,
  p_new_session_digest TEXT,
  p_new_refresh_digest TEXT,
  p_access_expires_at TIMESTAMPTZ,
  p_refresh_expires_at TIMESTAMPTZ,
  p_idempotency_digest TEXT,
  p_request_digest TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE (
  session_id UUID,
  rotation_generation BIGINT,
  outcome_code TEXT,
  affected_count INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  current_session identity_sessions%ROWTYPE;
  existing_operation identity_session_lifecycle_operations%ROWTYPE;
  created_session_id UUID := gen_random_uuid();
  changed_count INTEGER;
  v_now TIMESTAMPTZ := clock_timestamp();
BEGIN
  PERFORM a1_identity_session_assert_scope(
    p_organization_id, p_project_id, p_principal_id
  );
  IF NOT a1_identity_digest_valid(p_refresh_digest)
     OR NOT a1_identity_digest_valid(p_new_session_digest)
     OR NOT a1_identity_digest_valid(p_new_refresh_digest)
     OR NOT a1_identity_digest_valid(p_idempotency_digest)
     OR NOT a1_identity_digest_valid(p_request_digest)
     OR p_expected_generation < 0
     OR p_refresh_digest = p_new_refresh_digest
     OR p_new_session_digest = p_new_refresh_digest
     OR NOT a1_identity_public_metadata(p_metadata) THEN
    RAISE EXCEPTION 'identity refresh rotation is invalid'
      USING ERRCODE = '22023';
  END IF;

  PERFORM 1
    FROM identity_principals AS principal
   WHERE principal.id = p_principal_id
     AND principal.status = 'active'
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity refresh is unavailable'
      USING ERRCODE = '42501';
  END IF;

  SELECT session_row.*
    INTO current_session
    FROM identity_sessions AS session_row
   WHERE session_row.organization_id = p_organization_id
     AND session_row.project_id = p_project_id
     AND session_row.principal_id = p_principal_id
     AND session_row.refresh_digest = p_refresh_digest
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity refresh is unavailable'
      USING ERRCODE = '42501';
  END IF;

  SELECT operation.*
    INTO existing_operation
    FROM identity_session_lifecycle_operations AS operation
   WHERE operation.organization_id = p_organization_id
     AND operation.project_id = p_project_id
     AND operation.principal_id = p_principal_id
     AND operation.operation_kind = 'rotate'
     AND operation.idempotency_digest = p_idempotency_digest
   FOR UPDATE;
  IF current_session.status = 'rotated' THEN
    IF existing_operation.id IS NOT NULL
       AND existing_operation.request_digest = p_request_digest
       AND existing_operation.target_session_id = current_session.id
       AND current_session.rotation_generation = p_expected_generation THEN
      RETURN QUERY
      SELECT existing_operation.result_session_id,
             COALESCE(result_session.rotation_generation,
                      current_session.rotation_generation),
             existing_operation.outcome_code,
             existing_operation.affected_count
        FROM (SELECT 1) AS singleton
        LEFT JOIN identity_sessions AS result_session
          ON result_session.id = existing_operation.result_session_id;
      RETURN;
    END IF;

    UPDATE identity_sessions AS family_member
       SET status = 'revoked',
           revoked_at = COALESCE(family_member.revoked_at, v_now),
           revoke_reason_code = COALESCE(
             family_member.revoke_reason_code, 'refresh_reuse_detected'
           )
     WHERE family_member.principal_id = p_principal_id
       AND family_member.organization_id = p_organization_id
       AND family_member.project_id = p_project_id
       AND family_member.rotation_family_digest =
             current_session.rotation_family_digest
       AND family_member.status <> 'revoked';
    GET DIAGNOSTICS changed_count = ROW_COUNT;

    -- A conflicting reuse may deliberately repeat the original idempotency
    -- digest. The family revocation and audit must still commit even though
    -- the immutable operation key is already occupied by the first rotation.
    IF existing_operation.id IS NULL THEN
      INSERT INTO identity_session_lifecycle_operations (
        organization_id, project_id, principal_id, operation_kind,
        idempotency_digest, request_digest, target_session_id,
        outcome_code, affected_count, completed_at
      ) VALUES (
        p_organization_id, p_project_id, p_principal_id, 'rotate',
        p_idempotency_digest, p_request_digest, current_session.id,
        'refresh_reuse_detected', changed_count, v_now
      );
    END IF;

    PERFORM a1_identity_write_event(
      p_principal_id, p_organization_id, p_project_id, p_principal_id,
      'identity.session.refresh_reuse_detected', 'identity_session',
      current_session.id, p_request_digest,
      jsonb_build_object(
        'rotation_generation', current_session.rotation_generation,
        'revoked_count', changed_count,
        'reason_code', 'refresh_reuse_detected'
      )
    );
    RETURN QUERY
    SELECT NULL::UUID, current_session.rotation_generation,
           'refresh_reuse_detected'::TEXT, changed_count;
    RETURN;
  END IF;

  IF current_session.status = 'revoked' THEN
    IF existing_operation.id IS NOT NULL
       AND existing_operation.outcome_code = 'refresh_reuse_detected'
       AND existing_operation.request_digest = p_request_digest
       AND existing_operation.target_session_id = current_session.id
       AND current_session.rotation_generation = p_expected_generation THEN
      RETURN QUERY
      SELECT existing_operation.result_session_id,
             current_session.rotation_generation,
             existing_operation.outcome_code,
             existing_operation.affected_count;
      RETURN;
    END IF;
    RAISE EXCEPTION 'refresh_family_revoked'
      USING ERRCODE = '40001';
  END IF;
  IF existing_operation.id IS NOT NULL THEN
    RAISE EXCEPTION 'idempotency_conflict'
      USING ERRCODE = '23505';
  END IF;
  IF current_session.rotation_generation <> p_expected_generation THEN
    RAISE EXCEPTION 'refresh_generation_conflict'
      USING ERRCODE = '40001';
  END IF;
  IF current_session.status <> 'active'
     OR current_session.refresh_expires_at <= v_now THEN
    RAISE EXCEPTION 'identity refresh is unavailable'
      USING ERRCODE = '42501';
  END IF;
  IF p_access_expires_at <= v_now
     OR p_refresh_expires_at <= p_access_expires_at THEN
    RAISE EXCEPTION 'identity refresh rotation is invalid'
      USING ERRCODE = '22023';
  END IF;
  IF p_refresh_expires_at > current_session.refresh_expires_at THEN
    RAISE EXCEPTION 'refresh_expiration_conflict'
      USING ERRCODE = '40001';
  END IF;

  PERFORM 1
    FROM identity_credentials AS credential
   WHERE credential.principal_id = p_principal_id
     AND credential.id = current_session.credential_id
     AND credential.status = 'active'
     AND credential.login_enabled
   FOR KEY SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity refresh is unavailable'
      USING ERRCODE = '42501';
  END IF;

  UPDATE identity_sessions AS session_row
     SET status = 'rotated',
         rotated_at = v_now,
         rotated_to_session_id = created_session_id,
         rotation_idempotency_digest = p_idempotency_digest,
         rotation_request_digest = p_request_digest
   WHERE session_row.id = current_session.id
     AND session_row.status = 'active'
     AND session_row.rotation_generation = p_expected_generation;
  GET DIAGNOSTICS changed_count = ROW_COUNT;
  IF changed_count <> 1 THEN
    RAISE EXCEPTION 'refresh_generation_conflict'
      USING ERRCODE = '40001';
  END IF;

  INSERT INTO identity_sessions (
    id, principal_id, credential_id, organization_id, project_id,
    session_digest, refresh_digest, rotation_family_digest,
    rotation_generation, rotated_from_session_id,
    status, assurance_level, authenticated_at,
    expires_at, refresh_expires_at, last_seen_at, metadata
  ) VALUES (
    created_session_id, current_session.principal_id,
    current_session.credential_id, current_session.organization_id,
    current_session.project_id, p_new_session_digest, p_new_refresh_digest,
    current_session.rotation_family_digest,
    current_session.rotation_generation + 1, current_session.id,
    'active', current_session.assurance_level,
    current_session.authenticated_at, p_access_expires_at,
    p_refresh_expires_at, v_now, p_metadata
  );

  INSERT INTO identity_session_lifecycle_operations (
    organization_id, project_id, principal_id, operation_kind,
    idempotency_digest, request_digest, target_session_id,
    result_session_id, outcome_code, affected_count, completed_at
  ) VALUES (
    p_organization_id, p_project_id, p_principal_id, 'rotate',
    p_idempotency_digest, p_request_digest, current_session.id,
    created_session_id, 'rotated', 1, v_now
  );

  PERFORM a1_identity_write_event(
    p_principal_id, p_organization_id, p_project_id, p_principal_id,
    'identity.session.refresh_rotated', 'identity_session',
    current_session.id, p_request_digest,
    jsonb_build_object(
      'result_session_id', created_session_id,
      'rotation_generation', current_session.rotation_generation + 1
    )
  );
  RETURN QUERY
  SELECT created_session_id, current_session.rotation_generation + 1,
         'rotated'::TEXT, 1;
END;
$$;

CREATE OR REPLACE FUNCTION a1_revoke_identity_session(
  p_organization_id UUID,
  p_project_id UUID,
  p_principal_id UUID,
  p_actor_session_digest TEXT,
  p_target_session_id UUID,
  p_expected_generation BIGINT,
  p_recent_auth_max_age_seconds INTEGER,
  p_reason_code TEXT,
  p_idempotency_digest TEXT,
  p_request_digest TEXT
)
RETURNS TABLE (
  session_id UUID,
  rotation_generation BIGINT,
  outcome_code TEXT,
  affected_count INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  actor_session_id UUID;
  target_session identity_sessions%ROWTYPE;
  existing_operation identity_session_lifecycle_operations%ROWTYPE;
  result_outcome TEXT;
  changed_count INTEGER := 0;
  v_now TIMESTAMPTZ := clock_timestamp();
BEGIN
  PERFORM a1_identity_session_assert_scope(
    p_organization_id, p_project_id, p_principal_id
  );
  IF NOT a1_identity_digest_valid(p_actor_session_digest)
     OR NOT a1_identity_digest_valid(p_idempotency_digest)
     OR NOT a1_identity_digest_valid(p_request_digest)
     OR p_target_session_id IS NULL
     OR p_expected_generation < 0
     OR p_reason_code !~ '^[a-z][a-z0-9_.-]{1,63}$' THEN
    RAISE EXCEPTION 'identity session revocation is invalid'
      USING ERRCODE = '22023';
  END IF;

  PERFORM 1
    FROM identity_principals AS principal
   WHERE principal.id = p_principal_id
     AND principal.status = 'active'
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity session is unavailable'
      USING ERRCODE = '42501';
  END IF;

  SELECT operation.*
    INTO existing_operation
    FROM identity_session_lifecycle_operations AS operation
   WHERE operation.organization_id = p_organization_id
     AND operation.project_id = p_project_id
     AND operation.principal_id = p_principal_id
     AND operation.operation_kind = 'revoke_one'
     AND operation.idempotency_digest = p_idempotency_digest
   FOR UPDATE;
  IF FOUND THEN
    IF existing_operation.request_digest <> p_request_digest
       OR existing_operation.target_session_id <> p_target_session_id THEN
      RAISE EXCEPTION 'idempotency_conflict'
        USING ERRCODE = '23505';
    END IF;
    RETURN QUERY
    SELECT session_row.id, session_row.rotation_generation,
           existing_operation.outcome_code,
           existing_operation.affected_count
      FROM identity_sessions AS session_row
     WHERE session_row.id = existing_operation.target_session_id;
    RETURN;
  END IF;

  actor_session_id := a1_assert_recent_identity_authentication(
    p_organization_id, p_project_id, p_principal_id,
    p_actor_session_digest, p_recent_auth_max_age_seconds, 'aal1'
  );

  SELECT session_row.*
    INTO target_session
    FROM identity_sessions AS session_row
   WHERE session_row.organization_id = p_organization_id
     AND session_row.project_id = p_project_id
     AND session_row.principal_id = p_principal_id
     AND session_row.id = p_target_session_id
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity session is unavailable'
      USING ERRCODE = '42501';
  END IF;
  IF target_session.rotation_generation <> p_expected_generation THEN
    RAISE EXCEPTION 'session_generation_conflict'
      USING ERRCODE = '40001';
  END IF;

  UPDATE identity_sessions AS family_member
       SET status = 'revoked',
           revoked_at = v_now,
           revoke_reason_code = p_reason_code
   WHERE family_member.organization_id = p_organization_id
     AND family_member.project_id = p_project_id
     AND family_member.principal_id = p_principal_id
     AND family_member.rotation_family_digest =
           target_session.rotation_family_digest
     AND family_member.status <> 'revoked';
  GET DIAGNOSTICS changed_count = ROW_COUNT;
  IF changed_count = 0 THEN
    result_outcome := 'already_revoked';
  ELSE
    result_outcome := 'revoked';
  END IF;

  INSERT INTO identity_session_lifecycle_operations (
    organization_id, project_id, principal_id, operation_kind,
    idempotency_digest, request_digest, actor_session_id,
    target_session_id, outcome_code, affected_count, completed_at
  ) VALUES (
    p_organization_id, p_project_id, p_principal_id, 'revoke_one',
    p_idempotency_digest, p_request_digest, actor_session_id,
    target_session.id, result_outcome, changed_count, v_now
  );

  PERFORM a1_identity_write_event(
    p_principal_id, p_organization_id, p_project_id, p_principal_id,
    'identity.session.revoked_one', 'identity_session',
    target_session.id, p_request_digest,
    jsonb_build_object(
      'outcome_code', result_outcome,
      'reason_code', p_reason_code,
      'rotation_generation', target_session.rotation_generation
    )
  );
  RETURN QUERY
  SELECT target_session.id, target_session.rotation_generation,
         result_outcome, changed_count;
END;
$$;

CREATE OR REPLACE FUNCTION a1_revoke_all_identity_sessions(
  p_organization_id UUID,
  p_project_id UUID,
  p_principal_id UUID,
  p_actor_session_digest TEXT,
  p_keep_actor_session BOOLEAN,
  p_recent_auth_max_age_seconds INTEGER,
  p_reason_code TEXT,
  p_idempotency_digest TEXT,
  p_request_digest TEXT
)
RETURNS TABLE (
  session_id UUID,
  rotation_generation BIGINT,
  outcome_code TEXT,
  affected_count INTEGER
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  actor_session_id UUID;
  actor_generation BIGINT;
  existing_operation identity_session_lifecycle_operations%ROWTYPE;
  changed_count INTEGER;
  v_now TIMESTAMPTZ := clock_timestamp();
BEGIN
  PERFORM a1_identity_session_assert_scope(
    p_organization_id, p_project_id, p_principal_id
  );
  IF NOT a1_identity_digest_valid(p_actor_session_digest)
     OR NOT a1_identity_digest_valid(p_idempotency_digest)
     OR NOT a1_identity_digest_valid(p_request_digest)
     OR p_keep_actor_session IS NULL
     OR p_reason_code !~ '^[a-z][a-z0-9_.-]{1,63}$' THEN
    RAISE EXCEPTION 'identity session revocation is invalid'
      USING ERRCODE = '22023';
  END IF;

  PERFORM 1
    FROM identity_principals AS principal
   WHERE principal.id = p_principal_id
     AND principal.status = 'active'
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity session scope is unavailable'
      USING ERRCODE = '42501';
  END IF;

  SELECT operation.*
    INTO existing_operation
    FROM identity_session_lifecycle_operations AS operation
   WHERE operation.organization_id = p_organization_id
     AND operation.project_id = p_project_id
     AND operation.principal_id = p_principal_id
     AND operation.operation_kind = 'revoke_all'
     AND operation.idempotency_digest = p_idempotency_digest
   FOR UPDATE;
  IF FOUND THEN
    IF existing_operation.request_digest <> p_request_digest THEN
      RAISE EXCEPTION 'idempotency_conflict'
        USING ERRCODE = '23505';
    END IF;
    SELECT session_row.rotation_generation
      INTO actor_generation
      FROM identity_sessions AS session_row
     WHERE session_row.id = existing_operation.actor_session_id;
    RETURN QUERY
    SELECT existing_operation.actor_session_id, actor_generation,
           existing_operation.outcome_code,
           existing_operation.affected_count;
    RETURN;
  END IF;

  actor_session_id := a1_assert_recent_identity_authentication(
    p_organization_id, p_project_id, p_principal_id,
    p_actor_session_digest, p_recent_auth_max_age_seconds, 'aal1'
  );
  SELECT session_row.rotation_generation
    INTO actor_generation
    FROM identity_sessions AS session_row
   WHERE session_row.id = actor_session_id;

  UPDATE identity_sessions AS session_row
     SET status = 'revoked',
         revoked_at = v_now,
         revoke_reason_code = p_reason_code
   WHERE session_row.organization_id = p_organization_id
     AND session_row.project_id = p_project_id
     AND session_row.principal_id = p_principal_id
     AND session_row.status <> 'revoked'
     AND (NOT p_keep_actor_session OR session_row.id <> actor_session_id);
  GET DIAGNOSTICS changed_count = ROW_COUNT;

  INSERT INTO identity_session_lifecycle_operations (
    organization_id, project_id, principal_id, operation_kind,
    idempotency_digest, request_digest, actor_session_id,
    outcome_code, affected_count, completed_at
  ) VALUES (
    p_organization_id, p_project_id, p_principal_id, 'revoke_all',
    p_idempotency_digest, p_request_digest, actor_session_id,
    'revoked_all', changed_count, v_now
  );

  PERFORM a1_identity_write_event(
    p_principal_id, p_organization_id, p_project_id, p_principal_id,
    'identity.session.revoked_all', 'identity_session',
    actor_session_id, p_request_digest,
    jsonb_build_object(
      'affected_count', changed_count,
      'kept_actor_session', p_keep_actor_session,
      'reason_code', p_reason_code
    )
  );
  RETURN QUERY
  SELECT actor_session_id, actor_generation, 'revoked_all'::TEXT,
         changed_count;
END;
$$;

-- Migration 013 supersedes the access-only 012 login boundary while keeping
-- receipt consumption and its audit semantics in one transaction.
CREATE OR REPLACE FUNCTION a1_login_with_verified_identity_with_refresh(
  p_organization_id UUID,
  p_project_id UUID,
  p_receipt_digest TEXT,
  p_session_digest TEXT,
  p_refresh_digest TEXT,
  p_rotation_family_digest TEXT,
  p_access_expires_at TIMESTAMPTZ,
  p_refresh_expires_at TIMESTAMPTZ,
  p_idempotency_digest TEXT,
  p_request_digest TEXT,
  p_event_digest TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  created_session_id UUID;
  issued_session identity_sessions%ROWTYPE;
  attached_count INTEGER;
BEGIN
  IF NOT a1_identity_digest_valid(p_refresh_digest)
     OR p_refresh_expires_at <= p_access_expires_at THEN
    RAISE EXCEPTION 'identity verified login refresh is invalid'
      USING ERRCODE = '22023';
  END IF;

  created_session_id := a1_login_with_verified_identity(
    p_organization_id, p_project_id, p_receipt_digest,
    p_session_digest, p_rotation_family_digest, p_access_expires_at,
    p_idempotency_digest, p_request_digest, p_event_digest, p_metadata
  );

  SELECT session_row.*
    INTO issued_session
    FROM identity_sessions AS session_row
   WHERE session_row.id = created_session_id
     AND session_row.organization_id = p_organization_id
     AND session_row.project_id = p_project_id
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity verified login session is unavailable'
      USING ERRCODE = '42501';
  END IF;

  IF issued_session.refresh_digest IS NOT NULL THEN
    IF issued_session.refresh_digest <> p_refresh_digest
       OR issued_session.refresh_expires_at <> p_refresh_expires_at THEN
      RAISE EXCEPTION 'idempotency_conflict'
        USING ERRCODE = '23505';
    END IF;
    RETURN created_session_id;
  END IF;

  UPDATE identity_sessions AS session_row
     SET refresh_digest = p_refresh_digest,
         refresh_expires_at = p_refresh_expires_at
   WHERE session_row.id = created_session_id
     AND session_row.refresh_digest IS NULL
     AND session_row.refresh_expires_at IS NULL;
  GET DIAGNOSTICS attached_count = ROW_COUNT;
  IF attached_count <> 1 THEN
    RAISE EXCEPTION 'identity verified login session conflict'
      USING ERRCODE = '40001';
  END IF;

  PERFORM a1_identity_write_event(
    issued_session.principal_id, p_organization_id, p_project_id,
    issued_session.principal_id,
    'identity.session.verified_login_refresh_attached',
    'identity_session', created_session_id, p_request_digest,
    jsonb_build_object('rotation_generation', 0)
  );
  RETURN created_session_id;
END;
$$;

-- The 012 recovery mutation remains the receipt/state transition primitive,
-- but its access-only runtime grant is replaced by this refresh-aware wrapper.
CREATE OR REPLACE FUNCTION a1_recover_verified_identity_with_refresh(
  p_organization_id UUID,
  p_project_id UUID,
  p_receipt_digest TEXT,
  p_session_digest TEXT,
  p_refresh_digest TEXT,
  p_rotation_family_digest TEXT,
  p_access_expires_at TIMESTAMPTZ,
  p_refresh_expires_at TIMESTAMPTZ,
  p_idempotency_digest TEXT,
  p_request_digest TEXT,
  p_event_digest TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  created_session_id UUID;
  issued_session identity_sessions%ROWTYPE;
  attached_count INTEGER;
BEGIN
  IF NOT a1_identity_digest_valid(p_refresh_digest)
     OR p_refresh_expires_at <= p_access_expires_at THEN
    RAISE EXCEPTION 'identity verified recovery refresh is invalid'
      USING ERRCODE = '22023';
  END IF;

  created_session_id := a1_recover_verified_identity(
    p_organization_id, p_project_id, p_receipt_digest,
    p_session_digest, p_rotation_family_digest, p_access_expires_at,
    p_idempotency_digest, p_request_digest, p_event_digest, p_metadata
  );

  SELECT session_row.*
    INTO issued_session
    FROM identity_sessions AS session_row
   WHERE session_row.id = created_session_id
     AND session_row.organization_id = p_organization_id
     AND session_row.project_id = p_project_id
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity verified recovery session is unavailable'
      USING ERRCODE = '42501';
  END IF;

  IF issued_session.refresh_digest IS NOT NULL THEN
    IF issued_session.refresh_digest <> p_refresh_digest
       OR issued_session.refresh_expires_at <> p_refresh_expires_at THEN
      RAISE EXCEPTION 'idempotency_conflict'
        USING ERRCODE = '23505';
    END IF;
    RETURN created_session_id;
  END IF;

  UPDATE identity_sessions AS session_row
     SET refresh_digest = p_refresh_digest,
         refresh_expires_at = p_refresh_expires_at
   WHERE session_row.id = created_session_id
     AND session_row.refresh_digest IS NULL
     AND session_row.refresh_expires_at IS NULL;
  GET DIAGNOSTICS attached_count = ROW_COUNT;
  IF attached_count <> 1 THEN
    RAISE EXCEPTION 'identity verified recovery session conflict'
      USING ERRCODE = '40001';
  END IF;

  PERFORM a1_identity_write_event(
    issued_session.principal_id, p_organization_id, p_project_id,
    issued_session.principal_id,
    'identity.session.verified_recovery_refresh_attached',
    'identity_session', created_session_id, p_request_digest,
    jsonb_build_object('rotation_generation', 0)
  );
  RETURN created_session_id;
END;
$$;

CREATE OR REPLACE FUNCTION a1_invalidate_identity_sessions_for_recovery(
  p_organization_id UUID,
  p_project_id UUID,
  p_principal_id UUID,
  p_recovery_session_id UUID,
  p_receipt_digest TEXT,
  p_request_digest TEXT,
  p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  receipt identity_verification_receipts%ROWTYPE;
  existing_operation identity_session_lifecycle_operations%ROWTYPE;
  invalidated_count INTEGER;
BEGIN
  PERFORM a1_assert_role_nobypassrls(session_user);
  IF NOT a1_identity_digest_valid(p_receipt_digest)
     OR NOT a1_identity_digest_valid(p_request_digest)
     OR p_organization_id IS NULL
     OR p_project_id IS NULL
     OR p_principal_id IS NULL
     OR p_recovery_session_id IS NULL THEN
    RAISE EXCEPTION 'identity recovery invalidation is invalid'
      USING ERRCODE = '22023';
  END IF;

  SELECT receipt_row.*
    INTO receipt
    FROM identity_verification_receipts AS receipt_row
   WHERE receipt_row.organization_id = p_organization_id
     AND receipt_row.project_id = p_project_id
     AND receipt_row.principal_id = p_principal_id
     AND receipt_row.receipt_digest = p_receipt_digest
     AND receipt_row.status = 'consumed'
     AND receipt_row.purpose = 'account_recovery'
     AND receipt_row.mutation_kind = 'recovery'
     AND receipt_row.mutation_result_id = p_recovery_session_id;
  IF NOT FOUND OR receipt.request_digest <> p_request_digest THEN
    RAISE EXCEPTION 'identity recovery proof is unavailable'
      USING ERRCODE = '42501';
  END IF;

  PERFORM 1
    FROM identity_principals AS principal
   WHERE principal.id = p_principal_id
     AND principal.status = 'active'
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity recovery principal is unavailable'
      USING ERRCODE = '42501';
  END IF;

  PERFORM 1
    FROM identity_sessions AS recovery_session
   WHERE recovery_session.id = p_recovery_session_id
     AND recovery_session.principal_id = p_principal_id
     AND recovery_session.organization_id = p_organization_id
     AND recovery_session.project_id = p_project_id
     AND recovery_session.status = 'active'
     AND recovery_session.assurance_level IN ('aal2', 'aal3')
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity recovery session is unavailable'
      USING ERRCODE = '42501';
  END IF;

  SELECT operation.*
    INTO existing_operation
    FROM identity_session_lifecycle_operations AS operation
   WHERE operation.organization_id = p_organization_id
     AND operation.project_id = p_project_id
     AND operation.principal_id = p_principal_id
     AND operation.operation_kind = 'recovery_invalidate'
     AND operation.idempotency_digest = p_receipt_digest
   FOR UPDATE;
  IF FOUND THEN
    IF existing_operation.request_digest <> p_request_digest
       OR existing_operation.result_session_id <> p_recovery_session_id THEN
      RAISE EXCEPTION 'idempotency_conflict'
        USING ERRCODE = '23505';
    END IF;
    RETURN existing_operation.affected_count;
  END IF;

  UPDATE identity_sessions AS session_row
     SET status = 'revoked',
         revoked_at = p_now,
         revoke_reason_code = 'account_recovery'
   WHERE session_row.principal_id = p_principal_id
     AND session_row.organization_id = p_organization_id
     AND session_row.project_id = p_project_id
     AND session_row.id <> p_recovery_session_id
     AND session_row.status <> 'revoked';
  GET DIAGNOSTICS invalidated_count = ROW_COUNT;

  INSERT INTO identity_session_lifecycle_operations (
    organization_id, project_id, principal_id, operation_kind,
    idempotency_digest, request_digest, result_session_id,
    outcome_code, affected_count, completed_at
  ) VALUES (
    p_organization_id, p_project_id, p_principal_id,
    'recovery_invalidate', p_receipt_digest, p_request_digest,
    p_recovery_session_id, 'recovery_invalidated', invalidated_count, p_now
  );

  PERFORM a1_identity_write_event(
    p_principal_id, p_organization_id, p_project_id, p_principal_id,
    'identity.session.recovery_invalidated', 'identity_session',
    p_recovery_session_id, p_request_digest,
    jsonb_build_object(
      'invalidated_count', invalidated_count,
      'recovery_session_id', p_recovery_session_id,
      'reason_code', 'account_recovery'
    )
  );
  RETURN invalidated_count;
END;
$$;

CREATE OR REPLACE FUNCTION a1_identity_recovery_invalidate_sessions_trigger()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF OLD.status = 'verified'
     AND NEW.status = 'consumed'
     AND NEW.purpose = 'account_recovery'
     AND NEW.mutation_kind = 'recovery'
     AND NEW.principal_id IS NOT NULL
     AND NEW.mutation_result_id IS NOT NULL THEN
    PERFORM a1_invalidate_identity_sessions_for_recovery(
      NEW.organization_id, NEW.project_id, NEW.principal_id,
      NEW.mutation_result_id, NEW.receipt_digest,
      NEW.request_digest, clock_timestamp()
    );
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS identity_recovery_invalidate_sessions
  ON identity_verification_receipts;
CREATE TRIGGER identity_recovery_invalidate_sessions
AFTER UPDATE OF status ON identity_verification_receipts
FOR EACH ROW EXECUTE FUNCTION
  a1_identity_recovery_invalidate_sessions_trigger();

DROP TRIGGER IF EXISTS identity_session_lifecycle_operations_append_only
  ON identity_session_lifecycle_operations;
CREATE TRIGGER identity_session_lifecycle_operations_append_only
BEFORE UPDATE OR DELETE ON identity_session_lifecycle_operations
FOR EACH ROW EXECUTE FUNCTION a1_identity_reject_append_only_mutation();

ALTER TABLE identity_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_session_lifecycle_operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE identity_session_lifecycle_operations FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS identity_session_lifecycle_operations_scope_access
  ON identity_session_lifecycle_operations;
CREATE POLICY identity_session_lifecycle_operations_scope_access
  ON identity_session_lifecycle_operations
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

REVOKE ALL ON TABLE identity_sessions FROM PUBLIC;
REVOKE ALL ON TABLE identity_session_lifecycle_operations FROM PUBLIC;

REVOKE ALL ON FUNCTION a1_identity_session_assert_scope(UUID, UUID, UUID)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_assert_recent_identity_authentication(
  UUID, UUID, UUID, TEXT, INTEGER, TEXT
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_issue_identity_session_with_refresh(
  UUID, UUID, UUID, UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ,
  TEXT, TEXT, TEXT, JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_rotate_identity_session_refresh(
  UUID, UUID, UUID, TEXT, BIGINT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ,
  TEXT, TEXT, JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_revoke_identity_session(
  UUID, UUID, UUID, TEXT, UUID, BIGINT, INTEGER,
  TEXT, TEXT, TEXT
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_revoke_all_identity_sessions(
  UUID, UUID, UUID, TEXT, BOOLEAN, INTEGER,
  TEXT, TEXT, TEXT
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_login_with_verified_identity_with_refresh(
  UUID, UUID, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ,
  TEXT, TEXT, TEXT, JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_recover_verified_identity_with_refresh(
  UUID, UUID, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ,
  TEXT, TEXT, TEXT, JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_invalidate_identity_sessions_for_recovery(
  UUID, UUID, UUID, UUID, TEXT, TEXT, TIMESTAMPTZ
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_identity_recovery_invalidate_sessions_trigger()
  FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a1_runtime') THEN
    REVOKE ALL ON TABLE identity_sessions FROM a1_runtime;
    REVOKE ALL ON TABLE identity_session_lifecycle_operations FROM a1_runtime;
    -- These access-only functions predate refresh-family lifecycle support.
    -- Keeping EXECUTE would let production callers bypass generation fencing.
    REVOKE ALL ON FUNCTION a1_issue_identity_session(
      UUID, UUID, TEXT, TEXT, TIMESTAMPTZ,
      UUID, UUID, TEXT, TEXT, JSONB
    ) FROM a1_runtime;
    REVOKE ALL ON FUNCTION a1_consume_identity_recovery(
      TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, JSONB
    ) FROM a1_runtime;
    REVOKE ALL ON FUNCTION a1_login_with_verified_identity(
      UUID, UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ,
      TEXT, TEXT, TEXT, JSONB
    ) FROM a1_runtime;
    REVOKE ALL ON FUNCTION a1_recover_verified_identity(
      UUID, UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ,
      TEXT, TEXT, TEXT, JSONB
    ) FROM a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_assert_recent_identity_authentication(
      UUID, UUID, UUID, TEXT, INTEGER, TEXT
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_issue_identity_session_with_refresh(
      UUID, UUID, UUID, UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ,
      TEXT, TEXT, TEXT, JSONB
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_rotate_identity_session_refresh(
      UUID, UUID, UUID, TEXT, BIGINT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ,
      TEXT, TEXT, JSONB
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_revoke_identity_session(
      UUID, UUID, UUID, TEXT, UUID, BIGINT, INTEGER,
      TEXT, TEXT, TEXT
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_revoke_all_identity_sessions(
      UUID, UUID, UUID, TEXT, BOOLEAN, INTEGER,
      TEXT, TEXT, TEXT
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_login_with_verified_identity_with_refresh(
      UUID, UUID, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ,
      TEXT, TEXT, TEXT, JSONB
    ) TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_recover_verified_identity_with_refresh(
      UUID, UUID, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ,
      TEXT, TEXT, TEXT, JSONB
    ) TO a1_runtime;
  END IF;
END;
$$;

COMMIT;
