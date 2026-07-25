-- A1 PostgreSQL-authoritative organization/project/environment lifecycle.
-- The public runtime receives only keyed request digests and A3-safe payloads;
-- actor authority always comes from the server-resolved canonical principal.

BEGIN;

ALTER TABLE projects
  ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;
UPDATE projects
   SET archived_at = COALESCE(archived_at, updated_at, now())
 WHERE status = 'archived'
   AND archived_at IS NULL;
ALTER TABLE projects
  DROP CONSTRAINT IF EXISTS projects_archived_state_check;
ALTER TABLE projects
  ADD CONSTRAINT projects_archived_state_check CHECK (
    (status = 'archived' AND archived_at IS NOT NULL)
    OR (status <> 'archived' AND archived_at IS NULL)
  );

ALTER TABLE environments
  ADD COLUMN IF NOT EXISTS disabled_at TIMESTAMPTZ;
UPDATE environments
   SET disabled_at = COALESCE(disabled_at, updated_at, now())
 WHERE status = 'disabled'
   AND disabled_at IS NULL;
ALTER TABLE environments
  DROP CONSTRAINT IF EXISTS environments_disabled_state_check;
ALTER TABLE environments
  ADD CONSTRAINT environments_disabled_state_check CHECK (
    (status = 'disabled' AND disabled_at IS NOT NULL)
    OR (status <> 'disabled' AND disabled_at IS NULL)
  );

ALTER TABLE identity_organization_memberships
  DROP CONSTRAINT IF EXISTS identity_organization_memberships_role_check;
ALTER TABLE identity_organization_memberships
  ADD CONSTRAINT identity_organization_memberships_role_check CHECK (
    role IN (
      'owner', 'admin', 'security_admin', 'billing_admin', 'project_admin',
      'developer', 'reviewer', 'auditor', 'read_only_viewer',
      'service_account',
      -- Read-only compatibility for pre-v030 rows. New lifecycle writes reject
      -- these legacy aliases.
      'billing', 'viewer', 'member'
    )
  );

ALTER TABLE identity_project_memberships
  DROP CONSTRAINT IF EXISTS identity_project_memberships_role_check;
ALTER TABLE identity_project_memberships
  ADD CONSTRAINT identity_project_memberships_role_check CHECK (
    role IN (
      'owner', 'admin', 'developer', 'reviewer', 'auditor',
      'read_only_viewer', 'service_account',
      -- Read-only compatibility for pre-v030 rows.
      'operator', 'viewer', 'member'
    )
  );

-- Organization lifecycle events are valid without a project. Project-scoped
-- events must still provide the organization half of the composite scope.
ALTER TABLE identity_audit_events
  DROP CONSTRAINT IF EXISTS identity_audit_events_scope_pair_check;
ALTER TABLE identity_audit_events
  ADD CONSTRAINT identity_audit_events_scope_pair_check CHECK (
    project_id IS NULL OR organization_id IS NOT NULL
  );
ALTER TABLE identity_outbox
  DROP CONSTRAINT IF EXISTS identity_outbox_scope_pair_check;
ALTER TABLE identity_outbox
  ADD CONSTRAINT identity_outbox_scope_pair_check CHECK (
    project_id IS NULL OR organization_id IS NOT NULL
  );

DROP POLICY IF EXISTS identity_audit_events_scope_access
  ON identity_audit_events;
CREATE POLICY identity_audit_events_scope_access ON identity_audit_events
  USING (
    principal_id = a1_current_principal_id()
    OR actor_principal_id = a1_current_principal_id()
    OR (
      organization_id = a1_current_organization_id()
      AND (
        project_id IS NULL
        OR project_id = a1_current_project_id()
      )
    )
  )
  WITH CHECK (
    principal_id = a1_current_principal_id()
    OR (
      organization_id = a1_current_organization_id()
      AND (
        project_id IS NULL
        OR project_id = a1_current_project_id()
      )
    )
  );

DROP POLICY IF EXISTS identity_outbox_scope_access ON identity_outbox;
CREATE POLICY identity_outbox_scope_access ON identity_outbox
  USING (
    principal_id = a1_current_principal_id()
    OR (
      organization_id = a1_current_organization_id()
      AND (
        project_id IS NULL
        OR project_id = a1_current_project_id()
      )
    )
  )
  WITH CHECK (
    principal_id = a1_current_principal_id()
    OR (
      organization_id = a1_current_organization_id()
      AND (
        project_id IS NULL
        OR project_id = a1_current_project_id()
      )
    )
  );

CREATE OR REPLACE FUNCTION a1_identity_write_event(
  p_principal_id UUID,
  p_organization_id UUID,
  p_project_id UUID,
  p_actor_principal_id UUID,
  p_action TEXT,
  p_resource_type TEXT,
  p_resource_id UUID,
  p_request_digest TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  event_id UUID := gen_random_uuid();
  event_digest_value TEXT;
BEGIN
  IF p_action IS NULL OR btrim(p_action) = ''
     OR p_resource_type IS NULL OR btrim(p_resource_type) = ''
     OR (p_request_digest IS NOT NULL
       AND NOT a1_identity_digest_valid(p_request_digest))
     OR NOT a1_identity_public_metadata(p_metadata) THEN
    RAISE EXCEPTION 'identity event rejected'
      USING ERRCODE = '22023';
  END IF;
  IF p_project_id IS NOT NULL AND p_organization_id IS NULL THEN
    RAISE EXCEPTION 'identity project event requires organization scope'
      USING ERRCODE = '22023';
  END IF;

  event_digest_value := a1_oauth_digest(concat_ws(
    ':', event_id, p_principal_id, p_organization_id, p_project_id,
    p_actor_principal_id, p_action, p_resource_type, p_resource_id,
    p_request_digest, clock_timestamp()
  ));

  INSERT INTO identity_audit_events (
    id, principal_id, organization_id, project_id, actor_principal_id,
    action, resource_type, resource_id, request_digest, event_digest, metadata
  ) VALUES (
    event_id, p_principal_id, p_organization_id, p_project_id,
    p_actor_principal_id, p_action, p_resource_type, p_resource_id,
    p_request_digest, event_digest_value, p_metadata
  );
  INSERT INTO identity_outbox (
    principal_id, organization_id, project_id, event_type, aggregate_type,
    aggregate_id, event_digest, payload
  ) VALUES (
    p_principal_id, p_organization_id, p_project_id, p_action,
    p_resource_type, p_resource_id,
    a1_oauth_digest(event_digest_value || ':outbox'),
    p_metadata || jsonb_build_object(
      'audit_event_id', event_id,
      'request_digest_present', p_request_digest IS NOT NULL
    )
  );
  RETURN event_id;
END;
$$;

CREATE TABLE IF NOT EXISTS tenancy_mutation_receipts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL
    REFERENCES organizations(id) ON DELETE CASCADE,
  project_id UUID,
  actor_principal_id UUID NOT NULL
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  operation TEXT NOT NULL CHECK (
    operation IN (
      'organization.create',
      'project.create', 'project.update', 'project.archive', 'project.restore',
      'environment.create', 'environment.disable', 'environment.enable',
      'project_membership.set', 'project_membership.revoke'
    )
  ),
  scope_digest TEXT NOT NULL CHECK (a1_identity_digest_valid(scope_digest)),
  idempotency_key_digest TEXT NOT NULL
    CHECK (a1_identity_digest_valid(idempotency_key_digest)),
  request_digest TEXT NOT NULL CHECK (a1_identity_digest_valid(request_digest)),
  request_id TEXT NOT NULL CHECK (
    length(request_id) BETWEEN 1 AND 128
    AND request_id ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]*$'
  ),
  trace_id TEXT CHECK (
    trace_id IS NULL
    OR (
      length(trace_id) BETWEEN 1 AND 128
      AND trace_id ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]*$'
    )
  ),
  resource_type TEXT NOT NULL CHECK (
    resource_type IN (
      'organization', 'project', 'environment', 'project_membership'
    )
  ),
  resource_id UUID NOT NULL,
  response_payload JSONB NOT NULL
    CHECK (a1_identity_public_metadata(response_payload)),
  audit_event_id UUID NOT NULL
    REFERENCES identity_audit_events(id) ON DELETE RESTRICT,
  completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT tenancy_mutation_receipts_scope_key UNIQUE (
    actor_principal_id, operation, scope_digest, idempotency_key_digest
  ),
  CONSTRAINT tenancy_mutation_receipts_project_scope_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS tenancy_mutation_receipts_scope_created_idx
  ON tenancy_mutation_receipts(
    organization_id, project_id, actor_principal_id, created_at DESC
  );

DROP TRIGGER IF EXISTS tenancy_mutation_receipts_append_only
  ON tenancy_mutation_receipts;
CREATE TRIGGER tenancy_mutation_receipts_append_only
BEFORE UPDATE OR DELETE ON tenancy_mutation_receipts
FOR EACH ROW EXECUTE FUNCTION a1_identity_reject_append_only_mutation();

ALTER TABLE tenancy_mutation_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenancy_mutation_receipts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenancy_mutation_receipts_scope_access
  ON tenancy_mutation_receipts;
CREATE POLICY tenancy_mutation_receipts_scope_access
  ON tenancy_mutation_receipts
  USING (
    actor_principal_id = a1_current_principal_id()
    AND organization_id = a1_current_organization_id()
    AND (
      project_id IS NULL
      OR project_id = a1_current_project_id()
    )
  )
  WITH CHECK (
    actor_principal_id = a1_current_principal_id()
    AND organization_id = a1_current_organization_id()
    AND (
      project_id IS NULL
      OR project_id = a1_current_project_id()
    )
  );

CREATE OR REPLACE FUNCTION a1_tenancy_organization_role_valid(p_role TEXT)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
  SELECT p_role IN (
    'owner', 'admin', 'security_admin', 'billing_admin', 'project_admin',
    'developer', 'reviewer', 'auditor', 'read_only_viewer',
    'service_account'
  );
$$;

CREATE OR REPLACE FUNCTION a1_tenancy_project_role_valid(p_role TEXT)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
  SELECT p_role IN (
    'owner', 'admin', 'developer', 'reviewer', 'auditor',
    'read_only_viewer', 'service_account'
  );
$$;

CREATE OR REPLACE FUNCTION a1_tenancy_actor_active(p_actor_principal_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
  SELECT EXISTS (
    SELECT 1
      FROM identity_principals
     WHERE id = p_actor_principal_id
       AND status = 'active'
  );
$$;

CREATE OR REPLACE FUNCTION a1_tenancy_has_organization_role(
  p_actor_principal_id UUID,
  p_organization_id UUID,
  p_roles TEXT[]
)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
  SELECT EXISTS (
    SELECT 1
      FROM identity_organization_memberships membership
      JOIN organizations organization
        ON organization.id = membership.organization_id
     WHERE membership.organization_id = p_organization_id
       AND membership.principal_id = p_actor_principal_id
       AND membership.status = 'active'
       AND membership.role = ANY(p_roles)
       AND organization.status = 'active'
  );
$$;

CREATE OR REPLACE FUNCTION a1_tenancy_has_project_role(
  p_actor_principal_id UUID,
  p_organization_id UUID,
  p_project_id UUID,
  p_roles TEXT[]
)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
  SELECT EXISTS (
    SELECT 1
      FROM identity_project_memberships membership
      JOIN identity_organization_memberships organization_membership
        ON organization_membership.id = membership.organization_membership_id
       AND organization_membership.organization_id = membership.organization_id
       AND organization_membership.principal_id = membership.principal_id
      JOIN projects project
        ON project.organization_id = membership.organization_id
       AND project.id = membership.project_id
     WHERE membership.organization_id = p_organization_id
       AND membership.project_id = p_project_id
       AND membership.principal_id = p_actor_principal_id
       AND membership.status = 'active'
       AND membership.role = ANY(p_roles)
       AND organization_membership.status = 'active'
       AND project.status <> 'deleted'
  );
$$;

CREATE OR REPLACE FUNCTION a1_tenancy_organization_public(
  p_organization organizations
)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $$
  SELECT jsonb_build_object(
    'schema_version', 'ashr.clone.tenancy.v1',
    'organization_id', p_organization.id,
    'slug', p_organization.slug,
    'display_name', p_organization.display_name,
    'status', p_organization.status,
    'created_at', p_organization.created_at,
    'updated_at', p_organization.updated_at
  );
$$;

CREATE OR REPLACE FUNCTION a1_tenancy_project_public(p_project projects)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $$
  SELECT jsonb_build_object(
    'schema_version', 'ashr.clone.tenancy.v1',
    'organization_id', p_project.organization_id,
    'project_id', p_project.id,
    'slug', p_project.slug,
    'display_name', p_project.display_name,
    'status', p_project.status,
    'created_at', p_project.created_at,
    'updated_at', p_project.updated_at,
    'archived_at', p_project.archived_at
  );
$$;

CREATE OR REPLACE FUNCTION a1_tenancy_environment_public(
  p_environment environments
)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $$
  SELECT jsonb_build_object(
    'schema_version', 'ashr.clone.tenancy.v1',
    'organization_id', p_environment.organization_id,
    'project_id', p_environment.project_id,
    'environment_id', p_environment.id,
    'name', p_environment.name,
    'kind', p_environment.kind,
    'status', p_environment.status,
    'created_at', p_environment.created_at,
    'updated_at', p_environment.updated_at,
    'disabled_at', p_environment.disabled_at
  );
$$;

CREATE OR REPLACE FUNCTION a1_tenancy_project_membership_public(
  p_membership identity_project_memberships
)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $$
  SELECT jsonb_build_object(
    'schema_version', 'ashr.clone.tenancy.v1',
    'organization_id', p_membership.organization_id,
    'project_id', p_membership.project_id,
    'account_id', p_membership.principal_id,
    'role', p_membership.role,
    'status', p_membership.status,
    'created_at', p_membership.created_at,
    'updated_at', p_membership.updated_at,
    'activated_at', p_membership.activated_at,
    'revoked_at', p_membership.revoked_at
  );
$$;

CREATE OR REPLACE FUNCTION a1_tenancy_query(
  p_actor_principal_id UUID,
  p_operation TEXT,
  p_organization_id UUID DEFAULT NULL,
  p_project_id UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  result_value JSONB;
BEGIN
  IF NOT a1_tenancy_actor_active(p_actor_principal_id) THEN
    RAISE EXCEPTION 'tenancy_authentication_required'
      USING ERRCODE = '42501';
  END IF;
  PERFORM set_config(
    'app.a1_principal_id', p_actor_principal_id::TEXT, TRUE
  );
  PERFORM set_config(
    'app.a1_organization_id', COALESCE(p_organization_id::TEXT, ''), TRUE
  );
  PERFORM set_config(
    'app.a1_project_id', COALESCE(p_project_id::TEXT, ''), TRUE
  );

  CASE p_operation
    WHEN 'organization.list' THEN
      SELECT jsonb_build_object(
        'schema_version', 'ashr.clone.tenancy.v1',
        'items', COALESCE(
          jsonb_agg(
            a1_tenancy_organization_public(organization)
            ORDER BY organization.created_at, organization.id
          ),
          '[]'::JSONB
        ),
        'count', count(*)
      )
        INTO result_value
        FROM organizations organization
        JOIN identity_organization_memberships membership
          ON membership.organization_id = organization.id
       WHERE membership.principal_id = p_actor_principal_id
         AND membership.status = 'active'
         AND organization.status <> 'deleted';

    WHEN 'project.list' THEN
      IF p_organization_id IS NULL
         OR NOT a1_tenancy_has_organization_role(
           p_actor_principal_id,
           p_organization_id,
           ARRAY[
             'owner', 'admin', 'security_admin', 'billing_admin',
             'project_admin', 'developer', 'reviewer', 'auditor',
             'read_only_viewer', 'service_account',
             'billing', 'viewer', 'member'
           ]::TEXT[]
         ) THEN
        RAISE EXCEPTION 'tenancy_not_found'
          USING ERRCODE = 'P0002';
      END IF;
      SELECT jsonb_build_object(
        'schema_version', 'ashr.clone.tenancy.v1',
        'items', COALESCE(
          jsonb_agg(
            a1_tenancy_project_public(project)
            ORDER BY project.created_at, project.id
          ),
          '[]'::JSONB
        ),
        'count', count(*)
      )
        INTO result_value
        FROM projects project
       WHERE project.organization_id = p_organization_id
         AND project.status <> 'deleted';

    WHEN 'environment.list' THEN
      IF p_organization_id IS NULL OR p_project_id IS NULL
         OR NOT a1_tenancy_has_organization_role(
           p_actor_principal_id,
           p_organization_id,
           ARRAY[
             'owner', 'admin', 'security_admin', 'billing_admin',
             'project_admin', 'developer', 'reviewer', 'auditor',
             'read_only_viewer', 'service_account',
             'billing', 'viewer', 'member'
           ]::TEXT[]
         )
         OR NOT EXISTS (
           SELECT 1
             FROM projects
            WHERE organization_id = p_organization_id
              AND id = p_project_id
              AND status <> 'deleted'
         ) THEN
        RAISE EXCEPTION 'tenancy_not_found'
          USING ERRCODE = 'P0002';
      END IF;
      SELECT jsonb_build_object(
        'schema_version', 'ashr.clone.tenancy.v1',
        'items', COALESCE(
          jsonb_agg(
            a1_tenancy_environment_public(environment)
            ORDER BY environment.created_at, environment.id
          ),
          '[]'::JSONB
        ),
        'count', count(*)
      )
        INTO result_value
        FROM environments environment
       WHERE environment.organization_id = p_organization_id
         AND environment.project_id = p_project_id
         AND environment.status <> 'deleted';

    WHEN 'project_membership.list' THEN
      IF p_organization_id IS NULL OR p_project_id IS NULL
         OR NOT (
           a1_tenancy_has_organization_role(
             p_actor_principal_id,
             p_organization_id,
             ARRAY[
               'owner', 'admin', 'security_admin', 'project_admin'
             ]::TEXT[]
           )
           OR a1_tenancy_has_project_role(
             p_actor_principal_id,
             p_organization_id,
             p_project_id,
             ARRAY['owner', 'admin']::TEXT[]
           )
         ) THEN
        RAISE EXCEPTION 'tenancy_not_found'
          USING ERRCODE = 'P0002';
      END IF;
      SELECT jsonb_build_object(
        'schema_version', 'ashr.clone.tenancy.v1',
        'items', COALESCE(
          jsonb_agg(
            a1_tenancy_project_membership_public(membership)
            ORDER BY membership.created_at, membership.id
          ),
          '[]'::JSONB
        ),
        'count', count(*)
      )
        INTO result_value
        FROM identity_project_memberships membership
       WHERE membership.organization_id = p_organization_id
         AND membership.project_id = p_project_id;

    ELSE
      RAISE EXCEPTION 'tenancy_invalid_request'
        USING ERRCODE = '22023';
  END CASE;
  RETURN result_value;
END;
$$;

CREATE OR REPLACE FUNCTION a1_tenancy_mutate(
  p_actor_principal_id UUID,
  p_operation TEXT,
  p_organization_id UUID,
  p_project_id UUID,
  p_environment_id UUID,
  p_target_principal_id UUID,
  p_idempotency_key_digest TEXT,
  p_request_digest TEXT,
  p_request_id TEXT,
  p_trace_id TEXT,
  p_payload JSONB
)
RETURNS TABLE (
  result_payload JSONB,
  idempotent_replay BOOLEAN,
  completed_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
  scope_digest_value TEXT;
  existing_receipt tenancy_mutation_receipts%ROWTYPE;
  organization_record organizations%ROWTYPE;
  workspace_record workspaces%ROWTYPE;
  project_record projects%ROWTYPE;
  environment_record environments%ROWTYPE;
  membership_record identity_project_memberships%ROWTYPE;
  organization_membership_record identity_organization_memberships%ROWTYPE;
  resource_type_value TEXT;
  resource_id_value UUID;
  action_value TEXT;
  event_principal_id UUID;
  event_id UUID;
  result_value JSONB;
  event_metadata JSONB;
  now_value TIMESTAMPTZ := clock_timestamp();
  slug_value TEXT;
  display_name_value TEXT;
  environment_name_value TEXT;
  environment_kind_value TEXT;
  role_value TEXT;
  owner_count BIGINT;
  membership_exists BOOLEAN;
BEGIN
  IF NOT a1_tenancy_actor_active(p_actor_principal_id) THEN
    RAISE EXCEPTION 'tenancy_authentication_required'
      USING ERRCODE = '42501';
  END IF;
  IF p_operation NOT IN (
    'organization.create',
    'project.create', 'project.update', 'project.archive', 'project.restore',
    'environment.create', 'environment.disable', 'environment.enable',
    'project_membership.set', 'project_membership.revoke'
  )
     OR NOT a1_identity_digest_valid(p_idempotency_key_digest)
     OR NOT a1_identity_digest_valid(p_request_digest)
     OR p_request_id IS NULL
     OR length(p_request_id) NOT BETWEEN 1 AND 128
     OR p_request_id !~ '^[A-Za-z0-9][A-Za-z0-9._:/-]*$'
     OR (
       p_trace_id IS NOT NULL
       AND (
         length(p_trace_id) NOT BETWEEN 1 AND 128
         OR p_trace_id !~ '^[A-Za-z0-9][A-Za-z0-9._:/-]*$'
       )
     )
     OR p_payload IS NULL
     OR jsonb_typeof(p_payload) <> 'object'
     OR NOT a1_identity_public_metadata(p_payload) THEN
    RAISE EXCEPTION 'tenancy_invalid_request'
      USING ERRCODE = '22023';
  END IF;

  scope_digest_value := a1_oauth_digest(
    'tenancy-scope:' ||
    CASE
      WHEN p_operation = 'organization.create'
        THEN p_actor_principal_id::TEXT
      ELSE COALESCE(p_organization_id::TEXT, '')
    END
  );
  PERFORM pg_advisory_xact_lock(hashtextextended(concat_ws(
    ':', 'a1-tenancy', p_actor_principal_id, p_operation,
    scope_digest_value, p_idempotency_key_digest
  ), 0));

  SELECT *
    INTO existing_receipt
    FROM tenancy_mutation_receipts
   WHERE actor_principal_id = p_actor_principal_id
     AND operation = p_operation
     AND scope_digest = scope_digest_value
     AND idempotency_key_digest = p_idempotency_key_digest;
  IF FOUND THEN
    IF existing_receipt.request_digest <> p_request_digest THEN
      RAISE EXCEPTION 'tenancy_idempotency_conflict'
        USING ERRCODE = '23505';
    END IF;
    result_payload := existing_receipt.response_payload;
    idempotent_replay := TRUE;
    completed_at := existing_receipt.completed_at;
    RETURN NEXT;
    RETURN;
  END IF;

  PERFORM set_config(
    'app.a1_principal_id', p_actor_principal_id::TEXT, TRUE
  );
  PERFORM set_config(
    'app.a1_organization_id', COALESCE(p_organization_id::TEXT, ''), TRUE
  );
  PERFORM set_config(
    'app.a1_project_id', COALESCE(p_project_id::TEXT, ''), TRUE
  );

  CASE p_operation
    WHEN 'organization.create' THEN
      IF p_organization_id IS NOT NULL OR p_project_id IS NOT NULL
         OR p_environment_id IS NOT NULL OR p_target_principal_id IS NOT NULL
         OR p_payload - ARRAY['slug', 'display_name']::TEXT[] <> '{}'::JSONB THEN
        RAISE EXCEPTION 'tenancy_invalid_request'
          USING ERRCODE = '22023';
      END IF;
      slug_value := lower(btrim(p_payload->>'slug'));
      display_name_value := btrim(p_payload->>'display_name');
      IF slug_value IS NULL
         OR slug_value !~ '^[a-z][a-z0-9-]{1,62}[a-z0-9]$'
         OR display_name_value IS NULL
         OR length(display_name_value) NOT BETWEEN 1 AND 120 THEN
        RAISE EXCEPTION 'tenancy_invalid_request'
          USING ERRCODE = '22023';
      END IF;
      organization_record.id := gen_random_uuid();
      PERFORM set_config(
        'app.a1_organization_id', organization_record.id::TEXT, TRUE
      );
      INSERT INTO organizations (
        id, slug, display_name, status, metadata, created_at, updated_at
      ) VALUES (
        organization_record.id, slug_value, display_name_value, 'active',
        '{}'::JSONB, now_value, now_value
      )
      RETURNING * INTO organization_record;
      INSERT INTO workspaces (
        id, organization_id, slug, display_name, status, metadata,
        created_at, updated_at
      ) VALUES (
        gen_random_uuid(), organization_record.id, 'default', 'Default',
        'active', '{}'::JSONB, now_value, now_value
      )
      RETURNING * INTO workspace_record;
      INSERT INTO identity_organization_memberships (
        organization_id, principal_id, role, status, activated_at,
        metadata, created_at, updated_at
      ) VALUES (
        organization_record.id, p_actor_principal_id, 'owner', 'active',
        now_value, '{}'::JSONB, now_value, now_value
      );
      p_organization_id := organization_record.id;
      result_value := a1_tenancy_organization_public(organization_record);
      resource_type_value := 'organization';
      resource_id_value := organization_record.id;
      action_value := 'tenancy.organization.created';
      event_principal_id := p_actor_principal_id;

    WHEN 'project.create' THEN
      IF p_organization_id IS NULL OR p_project_id IS NOT NULL
         OR p_environment_id IS NOT NULL OR p_target_principal_id IS NOT NULL
         OR p_payload - ARRAY['slug', 'display_name']::TEXT[] <> '{}'::JSONB
         OR NOT a1_tenancy_has_organization_role(
           p_actor_principal_id,
           p_organization_id,
           ARRAY['owner', 'admin', 'project_admin']::TEXT[]
         ) THEN
        RAISE EXCEPTION 'tenancy_forbidden'
          USING ERRCODE = '42501';
      END IF;
      slug_value := lower(btrim(p_payload->>'slug'));
      display_name_value := btrim(p_payload->>'display_name');
      IF slug_value IS NULL
         OR slug_value !~ '^[a-z][a-z0-9-]{1,62}[a-z0-9]$'
         OR display_name_value IS NULL
         OR length(display_name_value) NOT BETWEEN 1 AND 120 THEN
        RAISE EXCEPTION 'tenancy_invalid_request'
          USING ERRCODE = '22023';
      END IF;
      SELECT *
        INTO workspace_record
        FROM workspaces
       WHERE organization_id = p_organization_id
         AND slug = 'default'
         AND status = 'active'
       ORDER BY created_at, id
       LIMIT 1
       FOR UPDATE;
      IF NOT FOUND THEN
        RAISE EXCEPTION 'tenancy_state_conflict'
          USING ERRCODE = '55000';
      END IF;
      INSERT INTO projects (
        id, organization_id, workspace_id, slug, display_name, status,
        metadata, created_at, updated_at
      ) VALUES (
        gen_random_uuid(), p_organization_id, workspace_record.id,
        slug_value, display_name_value, 'active', '{}'::JSONB,
        now_value, now_value
      )
      RETURNING * INTO project_record;
      SELECT *
        INTO organization_membership_record
        FROM identity_organization_memberships
       WHERE organization_id = p_organization_id
         AND principal_id = p_actor_principal_id
         AND status = 'active'
       FOR UPDATE;
      INSERT INTO identity_project_memberships (
        organization_id, project_id, principal_id,
        organization_membership_id, role, status, activated_at,
        metadata, created_at, updated_at
      ) VALUES (
        p_organization_id, project_record.id, p_actor_principal_id,
        organization_membership_record.id, 'owner', 'active', now_value,
        '{}'::JSONB, now_value, now_value
      );
      p_project_id := project_record.id;
      PERFORM set_config('app.a1_project_id', p_project_id::TEXT, TRUE);
      result_value := a1_tenancy_project_public(project_record);
      resource_type_value := 'project';
      resource_id_value := project_record.id;
      action_value := 'tenancy.project.created';
      event_principal_id := p_actor_principal_id;

    WHEN 'project.update', 'project.archive', 'project.restore' THEN
      IF p_organization_id IS NULL OR p_project_id IS NULL
         OR p_environment_id IS NOT NULL OR p_target_principal_id IS NOT NULL
         OR NOT (
           a1_tenancy_has_organization_role(
             p_actor_principal_id,
             p_organization_id,
             ARRAY['owner', 'admin', 'project_admin']::TEXT[]
           )
           OR a1_tenancy_has_project_role(
             p_actor_principal_id,
             p_organization_id,
             p_project_id,
             ARRAY['owner', 'admin']::TEXT[]
           )
         ) THEN
        RAISE EXCEPTION 'tenancy_not_found'
          USING ERRCODE = 'P0002';
      END IF;
      SELECT *
        INTO project_record
        FROM projects
       WHERE organization_id = p_organization_id
         AND id = p_project_id
         AND status <> 'deleted'
       FOR UPDATE;
      IF NOT FOUND THEN
        RAISE EXCEPTION 'tenancy_not_found'
          USING ERRCODE = 'P0002';
      END IF;
      IF p_operation = 'project.update' THEN
        IF project_record.status <> 'active' THEN
          RAISE EXCEPTION 'tenancy_state_conflict'
            USING ERRCODE = '55000';
        END IF;
        IF p_payload - ARRAY['slug', 'display_name']::TEXT[] <> '{}'::JSONB
           OR (
             NOT (p_payload ? 'slug')
             AND NOT (p_payload ? 'display_name')
           ) THEN
          RAISE EXCEPTION 'tenancy_invalid_request'
            USING ERRCODE = '22023';
        END IF;
        slug_value := COALESCE(
          lower(btrim(p_payload->>'slug')), project_record.slug
        );
        display_name_value := COALESCE(
          btrim(p_payload->>'display_name'), project_record.display_name
        );
        IF slug_value !~ '^[a-z][a-z0-9-]{1,62}[a-z0-9]$'
           OR length(display_name_value) NOT BETWEEN 1 AND 120 THEN
          RAISE EXCEPTION 'tenancy_invalid_request'
            USING ERRCODE = '22023';
        END IF;
        UPDATE projects
           SET slug = slug_value,
               display_name = display_name_value,
               updated_at = now_value
         WHERE organization_id = p_organization_id
           AND id = p_project_id
        RETURNING * INTO project_record;
        action_value := 'tenancy.project.updated';
      ELSIF p_operation = 'project.archive' THEN
        IF p_payload <> '{}'::JSONB OR project_record.status <> 'active' THEN
          RAISE EXCEPTION 'tenancy_state_conflict'
            USING ERRCODE = '55000';
        END IF;
        UPDATE projects
           SET status = 'archived',
               archived_at = now_value,
               updated_at = now_value
         WHERE organization_id = p_organization_id
           AND id = p_project_id
        RETURNING * INTO project_record;
        action_value := 'tenancy.project.archived';
      ELSE
        IF p_payload <> '{}'::JSONB OR project_record.status <> 'archived' THEN
          RAISE EXCEPTION 'tenancy_state_conflict'
            USING ERRCODE = '55000';
        END IF;
        UPDATE projects
           SET status = 'active',
               archived_at = NULL,
               updated_at = now_value
         WHERE organization_id = p_organization_id
           AND id = p_project_id
        RETURNING * INTO project_record;
        action_value := 'tenancy.project.restored';
      END IF;
      result_value := a1_tenancy_project_public(project_record);
      resource_type_value := 'project';
      resource_id_value := project_record.id;
      event_principal_id := p_actor_principal_id;

    WHEN 'environment.create' THEN
      IF p_organization_id IS NULL OR p_project_id IS NULL
         OR p_environment_id IS NOT NULL OR p_target_principal_id IS NOT NULL
         OR p_payload - ARRAY['name', 'kind']::TEXT[] <> '{}'::JSONB
         OR NOT (
           a1_tenancy_has_organization_role(
             p_actor_principal_id,
             p_organization_id,
             ARRAY['owner', 'admin', 'project_admin']::TEXT[]
           )
           OR a1_tenancy_has_project_role(
             p_actor_principal_id,
             p_organization_id,
             p_project_id,
             ARRAY['owner', 'admin', 'developer']::TEXT[]
           )
         ) THEN
        RAISE EXCEPTION 'tenancy_not_found'
          USING ERRCODE = 'P0002';
      END IF;
      IF NOT EXISTS (
        SELECT 1
          FROM projects
         WHERE organization_id = p_organization_id
           AND id = p_project_id
           AND status = 'active'
      ) THEN
        RAISE EXCEPTION 'tenancy_state_conflict'
          USING ERRCODE = '55000';
      END IF;
      environment_name_value := lower(btrim(p_payload->>'name'));
      environment_kind_value := lower(btrim(p_payload->>'kind'));
      IF environment_name_value IS NULL
         OR environment_name_value !~ '^[a-z][a-z0-9_-]{1,62}[a-z0-9]$'
         OR environment_kind_value NOT IN (
           'development', 'staging', 'production', 'sandbox'
         ) THEN
        RAISE EXCEPTION 'tenancy_invalid_request'
          USING ERRCODE = '22023';
      END IF;
      INSERT INTO environments (
        id, organization_id, project_id, name, kind, status, config,
        created_at, updated_at
      ) VALUES (
        gen_random_uuid(), p_organization_id, p_project_id,
        environment_name_value, environment_kind_value, 'active',
        '{}'::JSONB, now_value, now_value
      )
      RETURNING * INTO environment_record;
      p_environment_id := environment_record.id;
      result_value := a1_tenancy_environment_public(environment_record);
      resource_type_value := 'environment';
      resource_id_value := environment_record.id;
      action_value := 'tenancy.environment.created';
      event_principal_id := p_actor_principal_id;

    WHEN 'environment.disable', 'environment.enable' THEN
      IF p_organization_id IS NULL OR p_project_id IS NULL
         OR p_environment_id IS NULL OR p_target_principal_id IS NOT NULL
         OR p_payload <> '{}'::JSONB
         OR NOT (
           a1_tenancy_has_organization_role(
             p_actor_principal_id,
             p_organization_id,
             ARRAY['owner', 'admin', 'project_admin']::TEXT[]
           )
           OR a1_tenancy_has_project_role(
             p_actor_principal_id,
             p_organization_id,
             p_project_id,
             ARRAY['owner', 'admin', 'developer']::TEXT[]
           )
         ) THEN
        RAISE EXCEPTION 'tenancy_not_found'
          USING ERRCODE = 'P0002';
      END IF;
      SELECT *
        INTO environment_record
        FROM environments
       WHERE organization_id = p_organization_id
         AND project_id = p_project_id
         AND id = p_environment_id
         AND status <> 'deleted'
       FOR UPDATE;
      IF NOT FOUND THEN
        RAISE EXCEPTION 'tenancy_not_found'
          USING ERRCODE = 'P0002';
      END IF;
      IF p_operation = 'environment.disable' THEN
        IF environment_record.status <> 'active' THEN
          RAISE EXCEPTION 'tenancy_state_conflict'
            USING ERRCODE = '55000';
        END IF;
        UPDATE environments
           SET status = 'disabled',
               disabled_at = now_value,
               updated_at = now_value
         WHERE organization_id = p_organization_id
           AND project_id = p_project_id
           AND id = p_environment_id
        RETURNING * INTO environment_record;
        action_value := 'tenancy.environment.disabled';
      ELSE
        IF environment_record.status <> 'disabled'
           OR NOT EXISTS (
             SELECT 1
               FROM projects
              WHERE organization_id = p_organization_id
                AND id = p_project_id
                AND status = 'active'
           ) THEN
          RAISE EXCEPTION 'tenancy_state_conflict'
            USING ERRCODE = '55000';
        END IF;
        UPDATE environments
           SET status = 'active',
               disabled_at = NULL,
               updated_at = now_value
         WHERE organization_id = p_organization_id
           AND project_id = p_project_id
           AND id = p_environment_id
        RETURNING * INTO environment_record;
        action_value := 'tenancy.environment.enabled';
      END IF;
      result_value := a1_tenancy_environment_public(environment_record);
      resource_type_value := 'environment';
      resource_id_value := environment_record.id;
      event_principal_id := p_actor_principal_id;

    WHEN 'project_membership.set', 'project_membership.revoke' THEN
      IF p_organization_id IS NULL OR p_project_id IS NULL
         OR p_environment_id IS NOT NULL OR p_target_principal_id IS NULL
         OR NOT (
           a1_tenancy_has_organization_role(
             p_actor_principal_id,
             p_organization_id,
             ARRAY['owner', 'admin', 'security_admin']::TEXT[]
           )
           OR a1_tenancy_has_project_role(
             p_actor_principal_id,
             p_organization_id,
             p_project_id,
             ARRAY['owner', 'admin']::TEXT[]
           )
         ) THEN
        RAISE EXCEPTION 'tenancy_not_found'
          USING ERRCODE = 'P0002';
      END IF;
      PERFORM pg_advisory_xact_lock(hashtextextended(
        'a1-tenancy-project-owner:' || p_project_id::TEXT, 0
      ));
      IF NOT EXISTS (
        SELECT 1
          FROM projects
         WHERE organization_id = p_organization_id
           AND id = p_project_id
           AND status = 'active'
      ) THEN
        RAISE EXCEPTION 'tenancy_state_conflict'
          USING ERRCODE = '55000';
      END IF;
      SELECT *
        INTO organization_membership_record
        FROM identity_organization_memberships
       WHERE organization_id = p_organization_id
         AND principal_id = p_target_principal_id
         AND status = 'active'
       FOR UPDATE;
      IF NOT FOUND THEN
        RAISE EXCEPTION 'tenancy_not_found'
          USING ERRCODE = 'P0002';
      END IF;
      SELECT *
        INTO membership_record
        FROM identity_project_memberships
       WHERE organization_id = p_organization_id
         AND project_id = p_project_id
         AND principal_id = p_target_principal_id
       FOR UPDATE;
      membership_exists := FOUND;

      IF p_operation = 'project_membership.set' THEN
        IF p_payload - ARRAY['role']::TEXT[] <> '{}'::JSONB THEN
          RAISE EXCEPTION 'tenancy_invalid_request'
            USING ERRCODE = '22023';
        END IF;
        role_value := lower(btrim(p_payload->>'role'));
        IF NOT a1_tenancy_project_role_valid(role_value) THEN
          RAISE EXCEPTION 'tenancy_invalid_request'
            USING ERRCODE = '22023';
        END IF;
        IF membership_exists AND membership_record.status = 'active'
           AND membership_record.role = 'owner'
           AND role_value <> 'owner' THEN
          SELECT count(*)
            INTO owner_count
            FROM identity_project_memberships
           WHERE organization_id = p_organization_id
             AND project_id = p_project_id
             AND status = 'active'
             AND role = 'owner'
             AND principal_id <> p_target_principal_id;
          IF owner_count = 0 THEN
            RAISE EXCEPTION 'tenancy_last_owner'
              USING ERRCODE = 'P0003';
          END IF;
        END IF;
        INSERT INTO identity_project_memberships (
          organization_id, project_id, principal_id,
          organization_membership_id, role, status, activated_at,
          suspended_at, revoked_at, metadata, created_at, updated_at
        ) VALUES (
          p_organization_id, p_project_id, p_target_principal_id,
          organization_membership_record.id, role_value, 'active', now_value,
          NULL, NULL, '{}'::JSONB, now_value, now_value
        )
        ON CONFLICT (organization_id, project_id, principal_id)
        DO UPDATE SET
          organization_membership_id = EXCLUDED.organization_membership_id,
          role = EXCLUDED.role,
          status = 'active',
          activated_at = EXCLUDED.activated_at,
          suspended_at = NULL,
          revoked_at = NULL,
          metadata = '{}'::JSONB,
          updated_at = EXCLUDED.updated_at
        RETURNING * INTO membership_record;
        action_value := 'tenancy.project_membership.set';
      ELSE
        IF p_payload <> '{}'::JSONB OR NOT membership_exists
           OR membership_record.status <> 'active' THEN
          RAISE EXCEPTION 'tenancy_not_found'
            USING ERRCODE = 'P0002';
        END IF;
        IF membership_record.role = 'owner' THEN
          SELECT count(*)
            INTO owner_count
            FROM identity_project_memberships
           WHERE organization_id = p_organization_id
             AND project_id = p_project_id
             AND status = 'active'
             AND role = 'owner'
             AND principal_id <> p_target_principal_id;
          IF owner_count = 0 THEN
            RAISE EXCEPTION 'tenancy_last_owner'
              USING ERRCODE = 'P0003';
          END IF;
        END IF;
        UPDATE identity_project_memberships
           SET status = 'revoked',
               revoked_at = now_value,
               suspended_at = NULL,
               updated_at = now_value
         WHERE organization_id = p_organization_id
           AND project_id = p_project_id
           AND principal_id = p_target_principal_id
        RETURNING * INTO membership_record;
        action_value := 'tenancy.project_membership.revoked';
      END IF;
      result_value := a1_tenancy_project_membership_public(membership_record);
      resource_type_value := 'project_membership';
      resource_id_value := membership_record.id;
      event_principal_id := p_target_principal_id;

    ELSE
      RAISE EXCEPTION 'tenancy_invalid_request'
        USING ERRCODE = '22023';
  END CASE;

  event_metadata := jsonb_build_object(
    'schema_version', 'ashr.clone.tenancy.v1',
    'request_id', p_request_id,
    'trace_id', p_trace_id,
    'result', result_value
  );
  event_id := a1_identity_write_event(
    event_principal_id,
    p_organization_id,
    p_project_id,
    p_actor_principal_id,
    action_value,
    resource_type_value,
    resource_id_value,
    p_request_digest,
    event_metadata
  );

  INSERT INTO tenancy_mutation_receipts (
    organization_id, project_id, actor_principal_id, operation,
    scope_digest, idempotency_key_digest, request_digest,
    request_id, trace_id, resource_type, resource_id,
    response_payload, audit_event_id, completed_at, created_at
  ) VALUES (
    p_organization_id, p_project_id, p_actor_principal_id, p_operation,
    scope_digest_value, p_idempotency_key_digest, p_request_digest,
    p_request_id, p_trace_id, resource_type_value, resource_id_value,
    result_value, event_id, now_value, now_value
  );

  result_payload := result_value;
  idempotent_replay := FALSE;
  completed_at := now_value;
  RETURN NEXT;
END;
$$;

REVOKE ALL ON TABLE tenancy_mutation_receipts FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_tenancy_organization_role_valid(TEXT)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_tenancy_project_role_valid(TEXT)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_tenancy_actor_active(UUID)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_tenancy_has_organization_role(UUID, UUID, TEXT[])
  FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_tenancy_has_project_role(
  UUID, UUID, UUID, TEXT[]
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_tenancy_organization_public(organizations)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_tenancy_project_public(projects)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_tenancy_environment_public(environments)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_tenancy_project_membership_public(
  identity_project_memberships
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_tenancy_query(UUID, TEXT, UUID, UUID)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_tenancy_mutate(
  UUID, TEXT, UUID, UUID, UUID, UUID, TEXT, TEXT, TEXT, TEXT, JSONB
) FROM PUBLIC;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a1_runtime') THEN
    REVOKE ALL ON TABLE tenancy_mutation_receipts FROM a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_tenancy_query(UUID, TEXT, UUID, UUID)
      TO a1_runtime;
    GRANT EXECUTE ON FUNCTION a1_tenancy_mutate(
      UUID, TEXT, UUID, UUID, UUID, UUID, TEXT, TEXT, TEXT, TEXT, JSONB
    ) TO a1_runtime;
  END IF;
END;
$$;

COMMIT;
