-- A1 unified identity and account domain.
-- A global principal owns login credentials; tenant and project access are
-- expressed only through memberships. Identifiers are irreversible SHA-256
-- digests and credential secrets remain outside PostgreSQL.

BEGIN;

CREATE OR REPLACE FUNCTION a1_current_principal_id()
RETURNS UUID
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('app.a1_principal_id', TRUE), '')::UUID;
$$;

CREATE OR REPLACE FUNCTION a1_identity_digest_valid(p_digest TEXT)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
  SELECT p_digest IS NOT NULL AND p_digest ~ '^[a-f0-9]{64}$';
$$;

CREATE OR REPLACE FUNCTION a1_identity_provider_valid(p_provider TEXT)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
  SELECT p_provider IS NOT NULL
    AND length(p_provider) BETWEEN 2 AND 64
    AND p_provider ~ '^[a-z][a-z0-9_.-]*$';
$$;

CREATE OR REPLACE FUNCTION a1_identity_public_metadata(p_metadata JSONB)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  item RECORD;
  normalized_key TEXT;
BEGIN
  IF p_metadata IS NULL
     OR jsonb_typeof(p_metadata) IN ('null', 'string', 'number', 'boolean') THEN
    RETURN TRUE;
  END IF;
  IF jsonb_typeof(p_metadata) = 'array' THEN
    FOR item IN SELECT value FROM jsonb_array_elements(p_metadata)
    LOOP
      IF NOT a1_identity_public_metadata(item.value) THEN
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
      'email',
      'emailaddress',
      'phone',
      'phonenumber',
      'mobile',
      'subject',
      'providersubject',
      'openid',
      'unionid',
      'alipayuserid',
      'qqopenid',
      'password',
      'passwordhash',
      'accesskey',
      'accesstoken',
      'refreshtoken',
      'idtoken',
      'authorizationcode',
      'codeverifier',
      'clientsecret',
      'sessiontoken',
      'cookie',
      'state',
      'nonce'
    ) THEN
      RETURN FALSE;
    END IF;
    IF NOT a1_identity_public_metadata(item.value) THEN
      RETURN FALSE;
    END IF;
  END LOOP;
  RETURN TRUE;
END;
$$;

CREATE TABLE IF NOT EXISTS identity_principals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('pending', 'active', 'locked', 'suspended', 'merged', 'deleted')),
  display_label TEXT,
  locale TEXT,
  merged_into_principal_id UUID,
  merge_version BIGINT NOT NULL DEFAULT 0 CHECK (merge_version >= 0),
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_identity_public_metadata(metadata)),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  locked_at TIMESTAMPTZ,
  suspended_at TIMESTAMPTZ,
  merged_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  CONSTRAINT identity_principals_merge_state_check CHECK (
    (status = 'merged'
      AND merged_into_principal_id IS NOT NULL
      AND merged_at IS NOT NULL)
    OR (status <> 'merged'
      AND merged_into_principal_id IS NULL
      AND merged_at IS NULL)
  ),
  CONSTRAINT identity_principals_not_self_merged CHECK (
    merged_into_principal_id IS NULL OR merged_into_principal_id <> id
  ),
  CONSTRAINT identity_principals_merged_target_fk
    FOREIGN KEY (merged_into_principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS identity_principals_merge_target_idx
  ON identity_principals(merged_into_principal_id)
  WHERE merged_into_principal_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS identity_credentials (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  principal_id UUID NOT NULL,
  provider TEXT NOT NULL CHECK (a1_identity_provider_valid(provider)),
  provider_environment TEXT NOT NULL DEFAULT 'production'
    CHECK (provider_environment IN ('development', 'sandbox', 'production')),
  credential_kind TEXT NOT NULL
    CHECK (credential_kind IN (
      'federated', 'phone_otp', 'email_otp', 'email_password',
      'passkey', 'recovery', 'service'
    )),
  subject_digest TEXT NOT NULL CHECK (a1_identity_digest_valid(subject_digest)),
  secret_ref TEXT CHECK (a1_oauth_reference_only(secret_ref)),
  secret_fingerprint_digest TEXT
    CHECK (
      secret_fingerprint_digest IS NULL
      OR a1_identity_digest_valid(secret_fingerprint_digest)
    ),
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('pending', 'active', 'disabled', 'revoked', 'transferred')),
  login_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  verified_at TIMESTAMPTZ,
  last_authenticated_at TIMESTAMPTZ,
  disabled_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  transferred_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_identity_public_metadata(metadata)),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT identity_credentials_principal_id_key UNIQUE (principal_id, id),
  CONSTRAINT identity_credentials_global_identity_key UNIQUE (
    provider, provider_environment, subject_digest
  ),
  CONSTRAINT identity_credentials_principal_fk
    FOREIGN KEY (principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT identity_credentials_verified_active_check CHECK (
    status <> 'active' OR verified_at IS NOT NULL
  ),
  CONSTRAINT identity_credentials_disabled_state_check CHECK (
    (status = 'disabled' AND disabled_at IS NOT NULL)
    OR (status <> 'disabled' AND disabled_at IS NULL)
  ),
  CONSTRAINT identity_credentials_revoked_state_check CHECK (
    (status = 'revoked' AND revoked_at IS NOT NULL)
    OR (status <> 'revoked' AND revoked_at IS NULL)
  ),
  CONSTRAINT identity_credentials_transferred_state_check CHECK (
    (status = 'transferred' AND transferred_at IS NOT NULL)
    OR (status <> 'transferred' AND transferred_at IS NULL)
  ),
  CONSTRAINT identity_credentials_provider_kind_check CHECK (
    (provider = 'phone' AND credential_kind = 'phone_otp')
    OR (provider = 'email' AND credential_kind IN (
      'email_otp', 'email_password'
    ))
    OR (provider IN ('github', 'google', 'wechat', 'qq', 'alipay')
      AND credential_kind = 'federated')
    OR provider NOT IN (
      'github', 'google', 'wechat', 'qq', 'alipay', 'phone', 'email'
    )
  )
);

CREATE INDEX IF NOT EXISTS identity_credentials_principal_status_idx
  ON identity_credentials(principal_id, status, login_enabled, created_at);

CREATE TABLE IF NOT EXISTS identity_organization_memberships (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  principal_id UUID NOT NULL,
  role TEXT NOT NULL DEFAULT 'member'
    CHECK (role IN ('owner', 'admin', 'billing', 'developer', 'viewer', 'member')),
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('invited', 'active', 'suspended', 'revoked')),
  invited_by_principal_id UUID,
  activated_at TIMESTAMPTZ,
  suspended_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_identity_public_metadata(metadata)),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT identity_org_memberships_scope_key UNIQUE (
    organization_id, principal_id
  ),
  CONSTRAINT identity_org_memberships_org_id_key UNIQUE (
    organization_id, id
  ),
  CONSTRAINT identity_org_memberships_organization_fk
    FOREIGN KEY (organization_id)
    REFERENCES organizations(id) ON DELETE CASCADE,
  CONSTRAINT identity_org_memberships_principal_fk
    FOREIGN KEY (principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT identity_org_memberships_inviter_fk
    FOREIGN KEY (invited_by_principal_id)
    REFERENCES identity_principals(id) ON DELETE SET NULL,
  CONSTRAINT identity_org_memberships_state_check CHECK (
    (status = 'active' AND activated_at IS NOT NULL
      AND suspended_at IS NULL AND revoked_at IS NULL)
    OR (status = 'suspended' AND suspended_at IS NOT NULL
      AND revoked_at IS NULL)
    OR (status = 'revoked' AND revoked_at IS NOT NULL)
    OR status = 'invited'
  )
);

CREATE INDEX IF NOT EXISTS identity_org_memberships_principal_idx
  ON identity_organization_memberships(principal_id, status, organization_id);

CREATE TABLE IF NOT EXISTS identity_project_memberships (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  principal_id UUID NOT NULL,
  organization_membership_id UUID NOT NULL,
  role TEXT NOT NULL DEFAULT 'member'
    CHECK (role IN ('owner', 'admin', 'developer', 'operator', 'viewer', 'member')),
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('invited', 'active', 'suspended', 'revoked')),
  activated_at TIMESTAMPTZ,
  suspended_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_identity_public_metadata(metadata)),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT identity_project_memberships_scope_key UNIQUE (
    organization_id, project_id, principal_id
  ),
  CONSTRAINT identity_project_memberships_org_project_id_key UNIQUE (
    organization_id, project_id, id
  ),
  CONSTRAINT identity_project_memberships_project_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT identity_project_memberships_org_membership_fk
    FOREIGN KEY (organization_id, organization_membership_id)
    REFERENCES identity_organization_memberships(organization_id, id)
    ON DELETE CASCADE,
  CONSTRAINT identity_project_memberships_principal_fk
    FOREIGN KEY (principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT identity_project_memberships_state_check CHECK (
    (status = 'active' AND activated_at IS NOT NULL
      AND suspended_at IS NULL AND revoked_at IS NULL)
    OR (status = 'suspended' AND suspended_at IS NOT NULL
      AND revoked_at IS NULL)
    OR (status = 'revoked' AND revoked_at IS NOT NULL)
    OR status = 'invited'
  )
);

CREATE INDEX IF NOT EXISTS identity_project_memberships_principal_idx
  ON identity_project_memberships(
    principal_id, status, organization_id, project_id
  );

CREATE TABLE IF NOT EXISTS identity_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  principal_id UUID NOT NULL,
  credential_id UUID,
  organization_id UUID,
  project_id UUID,
  session_digest TEXT NOT NULL CHECK (a1_identity_digest_valid(session_digest)),
  rotation_family_digest TEXT NOT NULL
    CHECK (a1_identity_digest_valid(rotation_family_digest)),
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'rotated', 'revoked', 'expired')),
  assurance_level TEXT NOT NULL DEFAULT 'aal1'
    CHECK (assurance_level IN ('aal1', 'aal2', 'aal3')),
  authenticated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  last_seen_at TIMESTAMPTZ,
  rotated_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  revoke_reason_code TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_identity_public_metadata(metadata)),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT identity_sessions_digest_key UNIQUE (session_digest),
  CONSTRAINT identity_sessions_ttl_check CHECK (expires_at > authenticated_at),
  CONSTRAINT identity_sessions_principal_fk
    FOREIGN KEY (principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT identity_sessions_credential_scope_fk
    FOREIGN KEY (principal_id, credential_id)
    REFERENCES identity_credentials(principal_id, id) ON DELETE RESTRICT,
  CONSTRAINT identity_sessions_project_scope_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT identity_sessions_project_pair_check CHECK (
    (organization_id IS NULL AND project_id IS NULL)
    OR (organization_id IS NOT NULL AND project_id IS NOT NULL)
  ),
  CONSTRAINT identity_sessions_rotation_state_check CHECK (
    (status = 'rotated' AND rotated_at IS NOT NULL)
    OR (status <> 'rotated' AND rotated_at IS NULL)
  ),
  CONSTRAINT identity_sessions_revocation_state_check CHECK (
    (status = 'revoked' AND revoked_at IS NOT NULL
      AND revoke_reason_code IS NOT NULL)
    OR (status <> 'revoked' AND revoked_at IS NULL)
  )
);

CREATE INDEX IF NOT EXISTS identity_sessions_principal_active_idx
  ON identity_sessions(principal_id, expires_at DESC)
  WHERE status = 'active';

CREATE TABLE IF NOT EXISTS identity_link_conflicts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider TEXT NOT NULL CHECK (a1_identity_provider_valid(provider)),
  provider_environment TEXT NOT NULL
    CHECK (provider_environment IN ('development', 'sandbox', 'production')),
  subject_digest TEXT NOT NULL CHECK (a1_identity_digest_valid(subject_digest)),
  incumbent_principal_id UUID NOT NULL,
  requested_principal_id UUID NOT NULL,
  status TEXT NOT NULL DEFAULT 'open'
    CHECK (status IN ('open', 'approved', 'rejected', 'expired', 'superseded')),
  reason_code TEXT NOT NULL,
  requested_by_principal_id UUID,
  resolved_by_principal_id UUID,
  resolution_digest TEXT
    CHECK (resolution_digest IS NULL OR a1_identity_digest_valid(resolution_digest)),
  expires_at TIMESTAMPTZ NOT NULL,
  resolved_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_identity_public_metadata(metadata)),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT identity_link_conflicts_distinct_accounts_check CHECK (
    incumbent_principal_id <> requested_principal_id
  ),
  CONSTRAINT identity_link_conflicts_ttl_check CHECK (expires_at > created_at),
  CONSTRAINT identity_link_conflicts_resolution_check CHECK (
    (status = 'open' AND resolved_at IS NULL)
    OR (status <> 'open' AND resolved_at IS NOT NULL)
  ),
  CONSTRAINT identity_link_conflicts_incumbent_fk
    FOREIGN KEY (incumbent_principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT identity_link_conflicts_requested_fk
    FOREIGN KEY (requested_principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT identity_link_conflicts_requester_fk
    FOREIGN KEY (requested_by_principal_id)
    REFERENCES identity_principals(id) ON DELETE SET NULL,
  CONSTRAINT identity_link_conflicts_resolver_fk
    FOREIGN KEY (resolved_by_principal_id)
    REFERENCES identity_principals(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS identity_link_conflicts_open_key
  ON identity_link_conflicts(
    provider, provider_environment, subject_digest, requested_principal_id
  )
  WHERE status = 'open';

CREATE TABLE IF NOT EXISTS identity_account_merges (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_principal_id UUID NOT NULL,
  target_principal_id UUID NOT NULL,
  requested_by_principal_id UUID NOT NULL,
  approved_by_principal_id UUID,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'completed', 'rejected', 'failed')),
  reason_code TEXT NOT NULL,
  proof_digest TEXT NOT NULL CHECK (a1_identity_digest_valid(proof_digest)),
  result_digest TEXT
    CHECK (result_digest IS NULL OR a1_identity_digest_valid(result_digest)),
  requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_identity_public_metadata(metadata)),
  CONSTRAINT identity_account_merges_distinct_accounts_check CHECK (
    source_principal_id <> target_principal_id
  ),
  CONSTRAINT identity_account_merges_completion_check CHECK (
    (status = 'completed' AND completed_at IS NOT NULL
      AND result_digest IS NOT NULL)
    OR (status <> 'completed' AND completed_at IS NULL)
  ),
  CONSTRAINT identity_account_merges_source_fk
    FOREIGN KEY (source_principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT identity_account_merges_target_fk
    FOREIGN KEY (target_principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT identity_account_merges_requester_fk
    FOREIGN KEY (requested_by_principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT identity_account_merges_approver_fk
    FOREIGN KEY (approved_by_principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS identity_account_merges_pending_source_key
  ON identity_account_merges(source_principal_id)
  WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS identity_recovery_challenges (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  principal_id UUID NOT NULL,
  recovery_credential_id UUID NOT NULL,
  challenge_digest TEXT NOT NULL CHECK (a1_identity_digest_valid(challenge_digest)),
  proof_digest TEXT NOT NULL CHECK (a1_identity_digest_valid(proof_digest)),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'consumed', 'expired', 'revoked', 'failed')),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0 AND attempts <= 10),
  max_attempts INTEGER NOT NULL DEFAULT 5
    CHECK (max_attempts BETWEEN 1 AND 10),
  requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  request_context_digest TEXT NOT NULL
    CHECK (a1_identity_digest_valid(request_context_digest)),
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_identity_public_metadata(metadata)),
  CONSTRAINT identity_recovery_challenges_digest_key UNIQUE (challenge_digest),
  CONSTRAINT identity_recovery_challenges_ttl_check CHECK (
    expires_at > requested_at
  ),
  CONSTRAINT identity_recovery_challenges_consumed_check CHECK (
    (status = 'consumed' AND consumed_at IS NOT NULL)
    OR (status <> 'consumed' AND consumed_at IS NULL)
  ),
  CONSTRAINT identity_recovery_challenges_principal_fk
    FOREIGN KEY (principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT identity_recovery_challenges_credential_scope_fk
    FOREIGN KEY (principal_id, recovery_credential_id)
    REFERENCES identity_credentials(principal_id, id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS identity_recovery_challenges_pending_idx
  ON identity_recovery_challenges(expires_at, requested_at)
  WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS identity_audit_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  principal_id UUID,
  organization_id UUID,
  project_id UUID,
  actor_principal_id UUID,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id UUID,
  request_digest TEXT
    CHECK (request_digest IS NULL OR a1_identity_digest_valid(request_digest)),
  event_digest TEXT NOT NULL CHECK (a1_identity_digest_valid(event_digest)),
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_identity_public_metadata(metadata)),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT identity_audit_events_digest_key UNIQUE (event_digest),
  CONSTRAINT identity_audit_events_principal_fk
    FOREIGN KEY (principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT identity_audit_events_actor_fk
    FOREIGN KEY (actor_principal_id)
    REFERENCES identity_principals(id) ON DELETE SET NULL,
  CONSTRAINT identity_audit_events_project_scope_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT identity_audit_events_scope_pair_check CHECK (
    (organization_id IS NULL AND project_id IS NULL)
    OR (organization_id IS NOT NULL AND project_id IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS identity_audit_events_principal_created_idx
  ON identity_audit_events(principal_id, created_at DESC);
CREATE INDEX IF NOT EXISTS identity_audit_events_scope_created_idx
  ON identity_audit_events(organization_id, project_id, created_at DESC)
  WHERE organization_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS identity_outbox (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  principal_id UUID,
  organization_id UUID,
  project_id UUID,
  event_type TEXT NOT NULL,
  aggregate_type TEXT NOT NULL,
  aggregate_id UUID NOT NULL,
  event_digest TEXT NOT NULL CHECK (a1_identity_digest_valid(event_digest)),
  payload JSONB NOT NULL DEFAULT '{}'::JSONB
    CHECK (a1_identity_public_metadata(payload)),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'delivering', 'delivered', 'dead_letter')),
  available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  lease_owner_digest TEXT
    CHECK (lease_owner_digest IS NULL OR a1_identity_digest_valid(lease_owner_digest)),
  lease_expires_at TIMESTAMPTZ,
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  delivered_at TIMESTAMPTZ,
  last_error_code TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT identity_outbox_digest_key UNIQUE (event_digest),
  CONSTRAINT identity_outbox_principal_fk
    FOREIGN KEY (principal_id)
    REFERENCES identity_principals(id) ON DELETE RESTRICT,
  CONSTRAINT identity_outbox_project_scope_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT identity_outbox_scope_pair_check CHECK (
    (organization_id IS NULL AND project_id IS NULL)
    OR (organization_id IS NOT NULL AND project_id IS NOT NULL)
  ),
  CONSTRAINT identity_outbox_delivery_check CHECK (
    (status = 'delivered' AND delivered_at IS NOT NULL)
    OR (status <> 'delivered' AND delivered_at IS NULL)
  ),
  CONSTRAINT identity_outbox_lease_check CHECK (
    (status = 'delivering'
      AND lease_owner_digest IS NOT NULL
      AND lease_expires_at IS NOT NULL)
    OR (status <> 'delivering'
      AND lease_owner_digest IS NULL
      AND lease_expires_at IS NULL)
  )
);

CREATE INDEX IF NOT EXISTS identity_outbox_ready_idx
  ON identity_outbox(available_at, created_at)
  WHERE status = 'pending';

CREATE OR REPLACE FUNCTION a1_identity_reject_append_only_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION '% is append only', TG_TABLE_NAME
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION a1_identity_reject_hard_delete()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION '% requires an identity lifecycle transition', TG_TABLE_NAME
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION a1_identity_assert_membership_scope()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  membership identity_organization_memberships%ROWTYPE;
BEGIN
  SELECT *
    INTO membership
    FROM identity_organization_memberships
   WHERE organization_id = NEW.organization_id
     AND id = NEW.organization_membership_id
   FOR KEY SHARE;
  IF NOT FOUND OR membership.principal_id <> NEW.principal_id THEN
    RAISE EXCEPTION 'project membership principal does not match organization membership'
      USING ERRCODE = '23503';
  END IF;
  IF membership.status <> 'active' THEN
    RAISE EXCEPTION 'project membership requires an active organization membership'
      USING ERRCODE = '42501';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS identity_project_memberships_scope_guard
  ON identity_project_memberships;
CREATE TRIGGER identity_project_memberships_scope_guard
BEFORE INSERT OR UPDATE ON identity_project_memberships
FOR EACH ROW EXECUTE FUNCTION a1_identity_assert_membership_scope();

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
  IF (p_organization_id IS NULL) <> (p_project_id IS NULL) THEN
    RAISE EXCEPTION 'identity event scope must provide organization and project together'
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

CREATE OR REPLACE FUNCTION a1_link_identity_credential(
  p_principal_id UUID,
  p_provider TEXT,
  p_provider_environment TEXT,
  p_credential_kind TEXT,
  p_subject_digest TEXT,
  p_secret_ref TEXT DEFAULT NULL,
  p_secret_fingerprint_digest TEXT DEFAULT NULL,
  p_actor_principal_id UUID DEFAULT NULL,
  p_request_digest TEXT DEFAULT NULL,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE (
  credential_id UUID,
  linked_principal_id UUID,
  link_status TEXT,
  conflict_id UUID
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  principal identity_principals%ROWTYPE;
  incumbent identity_credentials%ROWTYPE;
  credential identity_credentials%ROWTYPE;
  conflict identity_link_conflicts%ROWTYPE;
  now_value TIMESTAMPTZ := clock_timestamp();
BEGIN
  PERFORM a1_assert_role_nobypassrls(session_user);
  IF NOT a1_identity_provider_valid(p_provider)
     OR p_provider_environment NOT IN ('development', 'sandbox', 'production')
     OR NOT a1_identity_digest_valid(p_subject_digest)
     OR NOT a1_oauth_reference_only(p_secret_ref)
     OR (p_secret_fingerprint_digest IS NOT NULL
       AND NOT a1_identity_digest_valid(p_secret_fingerprint_digest))
     OR NOT a1_identity_public_metadata(p_metadata) THEN
    RAISE EXCEPTION 'identity credential input rejected'
      USING ERRCODE = '22023';
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
    INTO incumbent
    FROM identity_credentials
   WHERE provider = p_provider
     AND provider_environment = p_provider_environment
     AND subject_digest = p_subject_digest
   FOR UPDATE;

  IF FOUND AND incumbent.principal_id <> p_principal_id THEN
    INSERT INTO identity_link_conflicts (
      provider, provider_environment, subject_digest,
      incumbent_principal_id, requested_principal_id,
      reason_code, requested_by_principal_id, expires_at, metadata
    ) VALUES (
      p_provider, p_provider_environment, p_subject_digest,
      incumbent.principal_id, p_principal_id,
      'global_identity_already_linked',
      COALESCE(p_actor_principal_id, p_principal_id),
      now_value + interval '30 minutes', p_metadata
    )
    ON CONFLICT (
      provider, provider_environment, subject_digest, requested_principal_id
    ) WHERE status = 'open'
    DO UPDATE SET expires_at = EXCLUDED.expires_at
    RETURNING * INTO conflict;

    PERFORM a1_identity_write_event(
      p_principal_id, NULL, NULL, p_actor_principal_id,
      'identity.credential.link_conflict', 'identity_link_conflict',
      conflict.id, p_request_digest,
      jsonb_build_object(
        'provider', p_provider,
        'provider_environment', p_provider_environment,
        'reason_code', conflict.reason_code
      )
    );
    RETURN QUERY SELECT NULL::UUID, p_principal_id, 'conflict', conflict.id;
    RETURN;
  END IF;

  IF FOUND THEN
    UPDATE identity_credentials
       SET last_authenticated_at = now_value,
           metadata = metadata || p_metadata,
           updated_at = now_value
     WHERE id = incumbent.id
    RETURNING * INTO credential;
  ELSE
    INSERT INTO identity_credentials (
      principal_id, provider, provider_environment, credential_kind,
      subject_digest, secret_ref, secret_fingerprint_digest,
      status, login_enabled, verified_at, last_authenticated_at, metadata
    ) VALUES (
      p_principal_id, p_provider, p_provider_environment, p_credential_kind,
      p_subject_digest, p_secret_ref, p_secret_fingerprint_digest,
      'active', TRUE, now_value, now_value, p_metadata
    )
    RETURNING * INTO credential;
  END IF;

  IF principal.status = 'pending' THEN
    UPDATE identity_principals
       SET status = 'active', updated_at = now_value
     WHERE id = principal.id;
  END IF;
  PERFORM a1_identity_write_event(
    p_principal_id, NULL, NULL, p_actor_principal_id,
    'identity.credential.linked', 'identity_credential',
    credential.id, p_request_digest,
    jsonb_build_object(
      'provider', p_provider,
      'provider_environment', p_provider_environment,
      'credential_kind', p_credential_kind
    )
  );
  RETURN QUERY SELECT credential.id, p_principal_id, 'linked', NULL::UUID;
END;
$$;

CREATE OR REPLACE FUNCTION a1_unlink_identity_credential(
  p_principal_id UUID,
  p_credential_id UUID,
  p_reason_code TEXT,
  p_actor_principal_id UUID DEFAULT NULL,
  p_request_digest TEXT DEFAULT NULL
)
RETURNS identity_credentials
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  credential identity_credentials%ROWTYPE;
  active_login_count INTEGER;
  now_value TIMESTAMPTZ := clock_timestamp();
BEGIN
  PERFORM a1_assert_role_nobypassrls(session_user);
  IF p_reason_code IS NULL OR btrim(p_reason_code) = '' THEN
    RAISE EXCEPTION 'credential unlink reason is required'
      USING ERRCODE = '22023';
  END IF;

  PERFORM 1
    FROM identity_principals
   WHERE id = p_principal_id
     AND status IN ('active', 'locked')
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'identity principal is not unlinkable'
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

  SELECT count(*)
    INTO active_login_count
    FROM identity_credentials
   WHERE principal_id = p_principal_id
     AND status = 'active'
     AND login_enabled;
  IF credential.login_enabled AND active_login_count <= 1 THEN
    RAISE EXCEPTION 'cannot unlink the last active login credential'
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
  UPDATE identity_sessions
     SET status = 'revoked',
         revoked_at = now_value,
         revoke_reason_code = 'credential_unlinked'
   WHERE principal_id = p_principal_id
     AND credential_id = p_credential_id
     AND status = 'active';

  PERFORM a1_identity_write_event(
    p_principal_id, NULL, NULL, p_actor_principal_id,
    'identity.credential.unlinked', 'identity_credential',
    credential.id, p_request_digest,
    jsonb_build_object(
      'provider', credential.provider,
      'reason_code', p_reason_code
    )
  );
  RETURN credential;
END;
$$;

CREATE OR REPLACE FUNCTION a1_issue_identity_session(
  p_principal_id UUID,
  p_credential_id UUID,
  p_session_digest TEXT,
  p_rotation_family_digest TEXT,
  p_expires_at TIMESTAMPTZ,
  p_organization_id UUID DEFAULT NULL,
  p_project_id UUID DEFAULT NULL,
  p_assurance_level TEXT DEFAULT 'aal1',
  p_request_digest TEXT DEFAULT NULL,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS identity_sessions
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  credential identity_credentials%ROWTYPE;
  issued identity_sessions%ROWTYPE;
BEGIN
  PERFORM a1_assert_role_nobypassrls(session_user);
  IF NOT a1_identity_digest_valid(p_session_digest)
     OR NOT a1_identity_digest_valid(p_rotation_family_digest)
     OR p_expires_at <= clock_timestamp()
     OR NOT a1_identity_public_metadata(p_metadata) THEN
    RAISE EXCEPTION 'identity session input rejected'
      USING ERRCODE = '22023';
  END IF;

  SELECT *
    INTO credential
    FROM identity_credentials
   WHERE principal_id = p_principal_id
     AND id = p_credential_id
     AND status = 'active'
     AND login_enabled
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'active identity credential not found'
      USING ERRCODE = '42501';
  END IF;

  IF p_organization_id IS NOT NULL THEN
    PERFORM 1
      FROM identity_organization_memberships
     WHERE organization_id = p_organization_id
       AND principal_id = p_principal_id
       AND status = 'active';
    IF NOT FOUND THEN
      RAISE EXCEPTION 'active organization membership required'
        USING ERRCODE = '42501';
    END IF;
    PERFORM 1
      FROM identity_project_memberships
     WHERE organization_id = p_organization_id
       AND project_id = p_project_id
       AND principal_id = p_principal_id
       AND status = 'active';
    IF NOT FOUND THEN
      RAISE EXCEPTION 'active project membership required'
        USING ERRCODE = '42501';
    END IF;
  ELSIF p_project_id IS NOT NULL THEN
    RAISE EXCEPTION 'project session requires organization scope'
      USING ERRCODE = '22023';
  END IF;

  INSERT INTO identity_sessions (
    principal_id, credential_id, organization_id, project_id,
    session_digest, rotation_family_digest, assurance_level,
    expires_at, metadata
  ) VALUES (
    p_principal_id, p_credential_id, p_organization_id, p_project_id,
    p_session_digest, p_rotation_family_digest, p_assurance_level,
    p_expires_at, p_metadata
  )
  RETURNING * INTO issued;
  PERFORM a1_identity_write_event(
    p_principal_id, p_organization_id, p_project_id, p_principal_id,
    'identity.session.issued', 'identity_session', issued.id,
    p_request_digest,
    jsonb_build_object(
      'assurance_level', p_assurance_level,
      'credential_id', p_credential_id
    )
  );
  RETURN issued;
END;
$$;

CREATE OR REPLACE FUNCTION a1_consume_identity_recovery(
  p_challenge_digest TEXT,
  p_proof_digest TEXT,
  p_session_digest TEXT,
  p_rotation_family_digest TEXT,
  p_session_expires_at TIMESTAMPTZ,
  p_request_context_digest TEXT,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS identity_sessions
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  challenge identity_recovery_challenges%ROWTYPE;
  issued identity_sessions%ROWTYPE;
  next_attempts INTEGER;
BEGIN
  PERFORM a1_assert_role_nobypassrls(session_user);
  IF NOT a1_identity_digest_valid(p_challenge_digest)
     OR NOT a1_identity_digest_valid(p_proof_digest)
     OR NOT a1_identity_digest_valid(p_session_digest)
     OR NOT a1_identity_digest_valid(p_rotation_family_digest)
     OR NOT a1_identity_digest_valid(p_request_context_digest)
     OR NOT a1_identity_public_metadata(p_metadata) THEN
    RAISE EXCEPTION 'identity recovery input rejected'
      USING ERRCODE = '22023';
  END IF;

  SELECT *
    INTO challenge
    FROM identity_recovery_challenges
   WHERE challenge_digest = p_challenge_digest
   FOR UPDATE;
  IF NOT FOUND OR challenge.status <> 'pending' THEN
    RAISE EXCEPTION 'identity recovery challenge unavailable'
      USING ERRCODE = 'P0002';
  END IF;
  IF challenge.expires_at <= clock_timestamp() THEN
    UPDATE identity_recovery_challenges
       SET status = 'expired'
     WHERE id = challenge.id;
    PERFORM a1_identity_write_event(
      challenge.principal_id, NULL, NULL, challenge.principal_id,
      'identity.recovery.rejected', 'identity_recovery_challenge',
      challenge.id, p_request_context_digest,
      jsonb_build_object('reason_code', 'challenge_expired')
    );
    RETURN NULL;
  END IF;
  IF challenge.request_context_digest <> p_request_context_digest THEN
    next_attempts := challenge.attempts + 1;
    UPDATE identity_recovery_challenges
       SET attempts = next_attempts,
           status = CASE
             WHEN next_attempts >= max_attempts THEN 'failed'
             ELSE status
           END
     WHERE id = challenge.id;
    PERFORM a1_identity_write_event(
      challenge.principal_id, NULL, NULL, challenge.principal_id,
      'identity.recovery.rejected', 'identity_recovery_challenge',
      challenge.id, p_request_context_digest,
      jsonb_build_object('reason_code', 'request_context_mismatch')
    );
    RETURN NULL;
  END IF;
  IF challenge.proof_digest <> p_proof_digest THEN
    next_attempts := challenge.attempts + 1;
    UPDATE identity_recovery_challenges
       SET attempts = next_attempts,
           status = CASE
             WHEN next_attempts >= max_attempts THEN 'failed'
             ELSE status
           END
     WHERE id = challenge.id;
    PERFORM a1_identity_write_event(
      challenge.principal_id, NULL, NULL, challenge.principal_id,
      'identity.recovery.rejected', 'identity_recovery_challenge',
      challenge.id, p_request_context_digest,
      jsonb_build_object('reason_code', 'proof_mismatch')
    );
    RETURN NULL;
  END IF;

  UPDATE identity_recovery_challenges
     SET status = 'consumed',
         consumed_at = clock_timestamp(),
         attempts = attempts + 1
   WHERE id = challenge.id;

  issued := a1_issue_identity_session(
    challenge.principal_id,
    challenge.recovery_credential_id,
    p_session_digest,
    p_rotation_family_digest,
    p_session_expires_at,
    NULL,
    NULL,
    'aal2',
    p_request_context_digest,
    p_metadata
  );
  PERFORM a1_identity_write_event(
    challenge.principal_id, NULL, NULL, challenge.principal_id,
    'identity.recovery.consumed', 'identity_recovery_challenge',
    challenge.id, p_request_context_digest,
    jsonb_build_object('session_id', issued.id)
  );
  RETURN issued;
END;
$$;

CREATE OR REPLACE FUNCTION a1_merge_identity_accounts(
  p_merge_id UUID,
  p_approved_by_principal_id UUID,
  p_result_digest TEXT,
  p_request_digest TEXT DEFAULT NULL
)
RETURNS identity_account_merges
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  merge_request identity_account_merges%ROWTYPE;
  first_principal_id UUID;
  second_principal_id UUID;
  now_value TIMESTAMPTZ := clock_timestamp();
BEGIN
  PERFORM a1_assert_role_nobypassrls(session_user);
  IF NOT a1_identity_digest_valid(p_result_digest) THEN
    RAISE EXCEPTION 'account merge result digest is required'
      USING ERRCODE = '22023';
  END IF;

  SELECT *
    INTO merge_request
    FROM identity_account_merges
   WHERE id = p_merge_id
   FOR UPDATE;
  IF NOT FOUND OR merge_request.status <> 'pending' THEN
    RAISE EXCEPTION 'pending account merge not found'
      USING ERRCODE = 'P0002';
  END IF;
  IF p_approved_by_principal_id IN (
    merge_request.source_principal_id,
    merge_request.target_principal_id
  ) THEN
    RAISE EXCEPTION 'account merge requires independent approval'
      USING ERRCODE = '42501';
  END IF;

  first_principal_id := LEAST(
    merge_request.source_principal_id,
    merge_request.target_principal_id
  );
  second_principal_id := GREATEST(
    merge_request.source_principal_id,
    merge_request.target_principal_id
  );
  PERFORM 1
    FROM identity_principals
   WHERE id IN (first_principal_id, second_principal_id)
   ORDER BY id
   FOR UPDATE;
  IF (SELECT count(*) FROM identity_principals
       WHERE id IN (first_principal_id, second_principal_id)
         AND status = 'active') <> 2 THEN
    RAISE EXCEPTION 'account merge requires two active principals'
      USING ERRCODE = '42501';
  END IF;

  UPDATE identity_sessions
     SET status = 'revoked',
         credential_id = NULL,
         revoked_at = now_value,
         revoke_reason_code = 'account_merged'
   WHERE principal_id IN (
       merge_request.source_principal_id,
       merge_request.target_principal_id
     )
     AND status = 'active';
  UPDATE identity_sessions
     SET credential_id = NULL
   WHERE principal_id = merge_request.source_principal_id
     AND credential_id IS NOT NULL;

  UPDATE identity_credentials
     SET principal_id = merge_request.target_principal_id,
         updated_at = now_value
   WHERE principal_id = merge_request.source_principal_id
     AND status IN ('pending', 'active', 'disabled');

  INSERT INTO identity_organization_memberships (
    organization_id, principal_id, role, status, activated_at, metadata
  )
  SELECT organization_id, merge_request.target_principal_id, role, status,
         activated_at, metadata
    FROM identity_organization_memberships
   WHERE principal_id = merge_request.source_principal_id
  ON CONFLICT (organization_id, principal_id) DO NOTHING;

  INSERT INTO identity_project_memberships (
    organization_id, project_id, principal_id, organization_membership_id,
    role, status, activated_at, metadata
  )
  SELECT source_project.organization_id, source_project.project_id,
         merge_request.target_principal_id, target_org.id,
         source_project.role, source_project.status,
         source_project.activated_at, source_project.metadata
    FROM identity_project_memberships AS source_project
    JOIN identity_organization_memberships AS target_org
      ON target_org.organization_id = source_project.organization_id
     AND target_org.principal_id = merge_request.target_principal_id
   WHERE source_project.principal_id = merge_request.source_principal_id
  ON CONFLICT (organization_id, project_id, principal_id) DO NOTHING;

  UPDATE identity_project_memberships
     SET status = 'revoked',
         revoked_at = now_value,
         updated_at = now_value
   WHERE principal_id = merge_request.source_principal_id
     AND status <> 'revoked';
  UPDATE identity_organization_memberships
     SET status = 'revoked',
         revoked_at = now_value,
         updated_at = now_value
   WHERE principal_id = merge_request.source_principal_id
     AND status <> 'revoked';
  UPDATE identity_principals
     SET status = 'merged',
         merged_into_principal_id = merge_request.target_principal_id,
         merged_at = now_value,
         merge_version = merge_version + 1,
         updated_at = now_value
   WHERE id = merge_request.source_principal_id;
  UPDATE identity_principals
     SET merge_version = merge_version + 1,
         updated_at = now_value
   WHERE id = merge_request.target_principal_id;
  UPDATE identity_account_merges
     SET status = 'completed',
         approved_by_principal_id = p_approved_by_principal_id,
         result_digest = p_result_digest,
         completed_at = now_value
   WHERE id = merge_request.id
  RETURNING * INTO merge_request;

  PERFORM a1_identity_write_event(
    merge_request.target_principal_id, NULL, NULL,
    p_approved_by_principal_id,
    'identity.account.merged', 'identity_account_merge',
    merge_request.id, p_request_digest,
    jsonb_build_object(
      'source_principal_id', merge_request.source_principal_id,
      'target_principal_id', merge_request.target_principal_id
    )
  );
  RETURN merge_request;
END;
$$;

CREATE OR REPLACE FUNCTION a1_claim_identity_outbox(
  p_lease_owner_digest TEXT,
  p_limit INTEGER DEFAULT 100,
  p_lease_seconds INTEGER DEFAULT 60
)
RETURNS SETOF identity_outbox
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  PERFORM a1_assert_role_nobypassrls(session_user);
  IF NOT a1_identity_digest_valid(p_lease_owner_digest)
     OR p_limit NOT BETWEEN 1 AND 500
     OR p_lease_seconds NOT BETWEEN 5 AND 900 THEN
    RAISE EXCEPTION 'identity outbox lease input rejected'
      USING ERRCODE = '22023';
  END IF;

  RETURN QUERY
  WITH candidates AS (
    SELECT id
      FROM identity_outbox
     WHERE (
       status = 'pending' AND available_at <= clock_timestamp()
     ) OR (
       status = 'delivering' AND lease_expires_at <= clock_timestamp()
     )
     ORDER BY available_at, created_at
     FOR UPDATE SKIP LOCKED
     LIMIT p_limit
  )
  UPDATE identity_outbox AS target
     SET status = 'delivering',
         lease_owner_digest = p_lease_owner_digest,
         lease_expires_at = clock_timestamp()
           + make_interval(secs => p_lease_seconds),
         attempts = target.attempts + 1
    FROM candidates
   WHERE target.id = candidates.id
  RETURNING target.*;
END;
$$;

DROP TRIGGER IF EXISTS identity_principals_reject_hard_delete
  ON identity_principals;
CREATE TRIGGER identity_principals_reject_hard_delete
BEFORE DELETE ON identity_principals
FOR EACH ROW EXECUTE FUNCTION a1_identity_reject_hard_delete();

DROP TRIGGER IF EXISTS identity_credentials_reject_hard_delete
  ON identity_credentials;
CREATE TRIGGER identity_credentials_reject_hard_delete
BEFORE DELETE ON identity_credentials
FOR EACH ROW EXECUTE FUNCTION a1_identity_reject_hard_delete();

DROP TRIGGER IF EXISTS identity_sessions_reject_hard_delete
  ON identity_sessions;
CREATE TRIGGER identity_sessions_reject_hard_delete
BEFORE DELETE ON identity_sessions
FOR EACH ROW EXECUTE FUNCTION a1_identity_reject_hard_delete();

DROP TRIGGER IF EXISTS identity_link_conflicts_append_only
  ON identity_link_conflicts;
CREATE TRIGGER identity_link_conflicts_append_only
BEFORE DELETE ON identity_link_conflicts
FOR EACH ROW EXECUTE FUNCTION a1_identity_reject_append_only_mutation();

DROP TRIGGER IF EXISTS identity_account_merges_append_only
  ON identity_account_merges;
CREATE TRIGGER identity_account_merges_append_only
BEFORE DELETE ON identity_account_merges
FOR EACH ROW EXECUTE FUNCTION a1_identity_reject_append_only_mutation();

DROP TRIGGER IF EXISTS identity_audit_events_append_only
  ON identity_audit_events;
CREATE TRIGGER identity_audit_events_append_only
BEFORE UPDATE OR DELETE ON identity_audit_events
FOR EACH ROW EXECUTE FUNCTION a1_identity_reject_append_only_mutation();

ALTER TABLE identity_principals ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_organization_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_project_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_link_conflicts ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_account_merges ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_recovery_challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_outbox ENABLE ROW LEVEL SECURITY;

ALTER TABLE identity_principals FORCE ROW LEVEL SECURITY;
ALTER TABLE identity_credentials FORCE ROW LEVEL SECURITY;
ALTER TABLE identity_organization_memberships FORCE ROW LEVEL SECURITY;
ALTER TABLE identity_project_memberships FORCE ROW LEVEL SECURITY;
ALTER TABLE identity_sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE identity_link_conflicts FORCE ROW LEVEL SECURITY;
ALTER TABLE identity_account_merges FORCE ROW LEVEL SECURITY;
ALTER TABLE identity_recovery_challenges FORCE ROW LEVEL SECURITY;
ALTER TABLE identity_audit_events FORCE ROW LEVEL SECURITY;
ALTER TABLE identity_outbox FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS identity_principals_self_access ON identity_principals;
DROP POLICY IF EXISTS identity_credentials_self_access ON identity_credentials;
DROP POLICY IF EXISTS identity_org_memberships_tenant_access
  ON identity_organization_memberships;
DROP POLICY IF EXISTS identity_project_memberships_tenant_access
  ON identity_project_memberships;
DROP POLICY IF EXISTS identity_sessions_self_access ON identity_sessions;
DROP POLICY IF EXISTS identity_link_conflicts_party_access
  ON identity_link_conflicts;
DROP POLICY IF EXISTS identity_account_merges_party_access
  ON identity_account_merges;
DROP POLICY IF EXISTS identity_recovery_challenges_self_access
  ON identity_recovery_challenges;
DROP POLICY IF EXISTS identity_audit_events_scope_access
  ON identity_audit_events;
DROP POLICY IF EXISTS identity_outbox_scope_access ON identity_outbox;

CREATE POLICY identity_principals_self_access ON identity_principals
  USING (
    id = a1_current_principal_id()
    OR merged_into_principal_id = a1_current_principal_id()
  )
  WITH CHECK (id = a1_current_principal_id());

CREATE POLICY identity_credentials_self_access ON identity_credentials
  USING (principal_id = a1_current_principal_id())
  WITH CHECK (principal_id = a1_current_principal_id());

CREATE POLICY identity_org_memberships_tenant_access
  ON identity_organization_memberships
  USING (
    organization_id = a1_current_organization_id()
    AND principal_id = a1_current_principal_id()
  )
  WITH CHECK (
    organization_id = a1_current_organization_id()
    AND principal_id = a1_current_principal_id()
  );

CREATE POLICY identity_project_memberships_tenant_access
  ON identity_project_memberships
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

CREATE POLICY identity_sessions_self_access ON identity_sessions
  USING (
    principal_id = a1_current_principal_id()
    AND (
      organization_id IS NULL
      OR (
        organization_id = a1_current_organization_id()
        AND project_id = a1_current_project_id()
      )
    )
  )
  WITH CHECK (
    principal_id = a1_current_principal_id()
    AND (
      organization_id IS NULL
      OR (
        organization_id = a1_current_organization_id()
        AND project_id = a1_current_project_id()
      )
    )
  );

CREATE POLICY identity_link_conflicts_party_access ON identity_link_conflicts
  USING (
    incumbent_principal_id = a1_current_principal_id()
    OR requested_principal_id = a1_current_principal_id()
  )
  WITH CHECK (requested_principal_id = a1_current_principal_id());

CREATE POLICY identity_account_merges_party_access ON identity_account_merges
  USING (
    source_principal_id = a1_current_principal_id()
    OR target_principal_id = a1_current_principal_id()
    OR requested_by_principal_id = a1_current_principal_id()
  )
  WITH CHECK (requested_by_principal_id = a1_current_principal_id());

CREATE POLICY identity_recovery_challenges_self_access
  ON identity_recovery_challenges
  USING (principal_id = a1_current_principal_id())
  WITH CHECK (principal_id = a1_current_principal_id());

CREATE POLICY identity_audit_events_scope_access ON identity_audit_events
  USING (
    principal_id = a1_current_principal_id()
    OR actor_principal_id = a1_current_principal_id()
    OR (
      organization_id = a1_current_organization_id()
      AND project_id = a1_current_project_id()
    )
  )
  WITH CHECK (
    principal_id = a1_current_principal_id()
    OR (
      organization_id = a1_current_organization_id()
      AND project_id = a1_current_project_id()
    )
  );

CREATE POLICY identity_outbox_scope_access ON identity_outbox
  USING (
    principal_id = a1_current_principal_id()
    OR (
      organization_id = a1_current_organization_id()
      AND project_id = a1_current_project_id()
    )
  )
  WITH CHECK (
    principal_id = a1_current_principal_id()
    OR (
      organization_id = a1_current_organization_id()
      AND project_id = a1_current_project_id()
    )
  );

REVOKE ALL ON FUNCTION a1_link_identity_credential(
  UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, UUID, TEXT, JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_unlink_identity_credential(
  UUID, UUID, TEXT, UUID, TEXT
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_issue_identity_session(
  UUID, UUID, TEXT, TEXT, TIMESTAMPTZ, UUID, UUID, TEXT, TEXT, JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_consume_identity_recovery(
  TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, JSONB
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_merge_identity_accounts(
  UUID, UUID, TEXT, TEXT
) FROM PUBLIC;
REVOKE ALL ON FUNCTION a1_claim_identity_outbox(
  TEXT, INTEGER, INTEGER
) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION a1_link_identity_credential(
  UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, UUID, TEXT, JSONB
) TO a1_runtime;
GRANT EXECUTE ON FUNCTION a1_unlink_identity_credential(
  UUID, UUID, TEXT, UUID, TEXT
) TO a1_runtime;
GRANT EXECUTE ON FUNCTION a1_issue_identity_session(
  UUID, UUID, TEXT, TEXT, TIMESTAMPTZ, UUID, UUID, TEXT, TEXT, JSONB
) TO a1_runtime;
GRANT EXECUTE ON FUNCTION a1_consume_identity_recovery(
  TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, JSONB
) TO a1_runtime;
GRANT EXECUTE ON FUNCTION a1_merge_identity_accounts(
  UUID, UUID, TEXT, TEXT
) TO a1_runtime;
GRANT EXECUTE ON FUNCTION a1_claim_identity_outbox(
  TEXT, INTEGER, INTEGER
) TO a1_runtime;

COMMIT;
