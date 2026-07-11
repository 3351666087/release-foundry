-- Digest-only identity session authentication boundary for FORCE RLS runtimes.

BEGIN;

CREATE OR REPLACE FUNCTION a1_authenticate_identity_session_digest(
  p_session_digest TEXT
)
RETURNS TABLE (
  principal_id UUID,
  session_id UUID,
  organization_id UUID,
  project_id UUID
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  PERFORM a1_assert_role_nobypassrls(session_user);

  IF NOT a1_identity_digest_valid(p_session_digest) THEN
    RETURN;
  END IF;

  RETURN QUERY
  SELECT
    identity_session.principal_id,
    identity_session.id,
    identity_session.organization_id,
    identity_session.project_id
    FROM identity_sessions AS identity_session
    JOIN identity_principals AS principal
      ON principal.id = identity_session.principal_id
     AND principal.status = 'active'
    JOIN identity_credentials AS credential
      ON credential.id = identity_session.credential_id
     AND credential.principal_id = identity_session.principal_id
     AND credential.status = 'active'
     AND credential.login_enabled
   WHERE identity_session.session_digest = p_session_digest
     AND identity_session.status = 'active'
     AND identity_session.expires_at > clock_timestamp()
     AND (
       (
         identity_session.organization_id IS NULL
         AND identity_session.project_id IS NULL
       )
       OR (
         identity_session.organization_id IS NOT NULL
         AND identity_session.project_id IS NOT NULL
         AND EXISTS (
           SELECT 1
             FROM identity_organization_memberships AS organization_membership
             JOIN identity_project_memberships AS project_membership
               ON project_membership.organization_id =
                    organization_membership.organization_id
              AND project_membership.organization_membership_id =
                    organization_membership.id
              AND project_membership.principal_id =
                    organization_membership.principal_id
              AND project_membership.project_id =
                    identity_session.project_id
              AND project_membership.status = 'active'
            WHERE organization_membership.organization_id =
                    identity_session.organization_id
              AND organization_membership.principal_id =
                    identity_session.principal_id
              AND organization_membership.status = 'active'
         )
       )
     )
   LIMIT 1;
END;
$$;

REVOKE ALL ON FUNCTION a1_authenticate_identity_session_digest(TEXT)
  FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a1_runtime') THEN
    GRANT EXECUTE ON FUNCTION a1_authenticate_identity_session_digest(TEXT)
      TO a1_runtime;
  END IF;
END;
$$;

COMMIT;
