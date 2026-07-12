-- Contract-supported PostgreSQL reference migration for ArtifactReference v2.
-- Production verification still requires multi-node PostgreSQL and object-store
-- failure injection. Application transactions must set all five a2.scope_*
-- settings before accessing these tables.

CREATE TABLE IF NOT EXISTS a2_artifact_reference_consumptions (
  nonce_hash text PRIMARY KEY,
  reference_id_hash text NOT NULL,
  authorization_hash text NOT NULL,
  issuer_hash text NOT NULL,
  key_id_hash text NOT NULL,
  issuer_key_target_hash text NOT NULL,
  audience_hash text NOT NULL,
  subject_hash text NOT NULL,
  evaluation_job_id_hash text NOT NULL,
  purpose text NOT NULL,
  organization_id text NOT NULL,
  tenant_id text NOT NULL,
  workspace_id text NOT NULL,
  project_id text NOT NULL,
  environment_id text NOT NULL,
  status text NOT NULL CHECK (
    status IN ('reserved', 'reading', 'resolved', 'failed_retryable', 'failed_terminal', 'revoked')
  ),
  reserved_at timestamptz NOT NULL,
  lease_owner text,
  lease_expires_at timestamptz,
  fencing_token bigint NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
  attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  completed_at timestamptz,
  failure_class text,
  receipt_hash text NOT NULL,
  public_safe boolean NOT NULL CHECK (public_safe)
);

CREATE TABLE IF NOT EXISTS a2_artifact_reference_events (
  event_id text PRIMARY KEY,
  nonce_hash text NOT NULL REFERENCES a2_artifact_reference_consumptions(nonce_hash),
  organization_id text NOT NULL,
  tenant_id text NOT NULL,
  workspace_id text NOT NULL,
  project_id text NOT NULL,
  environment_id text NOT NULL,
  event_type text NOT NULL,
  status text NOT NULL,
  lease_owner_hash text NOT NULL,
  fencing_token bigint NOT NULL CHECK (fencing_token >= 0),
  occurred_at timestamptz NOT NULL,
  details_hash text NOT NULL,
  previous_event_hash text NOT NULL,
  event_hash text NOT NULL,
  public_safe boolean NOT NULL CHECK (public_safe)
);

CREATE TABLE IF NOT EXISTS a2_artifact_reference_revocations (
  revocation_id text PRIMARY KEY,
  revocation_type text NOT NULL CHECK (
    revocation_type IN ('reference', 'job', 'issuer_key', 'tenant_project')
  ),
  target_hash text NOT NULL,
  organization_id text NOT NULL,
  tenant_id text NOT NULL,
  workspace_id text NOT NULL,
  project_id text NOT NULL,
  environment_id text NOT NULL,
  reason_code text NOT NULL,
  revoked_at timestamptz NOT NULL,
  UNIQUE (revocation_type, target_hash, tenant_id, project_id)
);

CREATE INDEX IF NOT EXISTS idx_a2_artifact_authorization_scope
  ON a2_artifact_reference_consumptions (tenant_id, project_id, status, reserved_at);
CREATE INDEX IF NOT EXISTS idx_a2_artifact_authorization_lease
  ON a2_artifact_reference_consumptions (status, lease_expires_at, reserved_at);
CREATE INDEX IF NOT EXISTS idx_a2_artifact_authorization_events
  ON a2_artifact_reference_events (nonce_hash, occurred_at, event_id);
CREATE INDEX IF NOT EXISTS idx_a2_artifact_authorization_revocations
  ON a2_artifact_reference_revocations (revocation_type, target_hash, tenant_id, project_id);

ALTER TABLE a2_artifact_reference_consumptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE a2_artifact_reference_consumptions FORCE ROW LEVEL SECURITY;
ALTER TABLE a2_artifact_reference_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE a2_artifact_reference_events FORCE ROW LEVEL SECURITY;
ALTER TABLE a2_artifact_reference_revocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE a2_artifact_reference_revocations FORCE ROW LEVEL SECURITY;

CREATE POLICY a2_artifact_consumption_scope ON a2_artifact_reference_consumptions
  USING (
    organization_id = current_setting('a2.scope_organization_id', true)
    AND tenant_id = current_setting('a2.scope_tenant_id', true)
    AND workspace_id = current_setting('a2.scope_workspace_id', true)
    AND project_id = current_setting('a2.scope_project_id', true)
    AND environment_id = current_setting('a2.scope_environment_id', true)
  )
  WITH CHECK (
    organization_id = current_setting('a2.scope_organization_id', true)
    AND tenant_id = current_setting('a2.scope_tenant_id', true)
    AND workspace_id = current_setting('a2.scope_workspace_id', true)
    AND project_id = current_setting('a2.scope_project_id', true)
    AND environment_id = current_setting('a2.scope_environment_id', true)
  );

CREATE POLICY a2_artifact_event_scope ON a2_artifact_reference_events
  USING (
    organization_id = current_setting('a2.scope_organization_id', true)
    AND tenant_id = current_setting('a2.scope_tenant_id', true)
    AND workspace_id = current_setting('a2.scope_workspace_id', true)
    AND project_id = current_setting('a2.scope_project_id', true)
    AND environment_id = current_setting('a2.scope_environment_id', true)
  )
  WITH CHECK (
    organization_id = current_setting('a2.scope_organization_id', true)
    AND tenant_id = current_setting('a2.scope_tenant_id', true)
    AND workspace_id = current_setting('a2.scope_workspace_id', true)
    AND project_id = current_setting('a2.scope_project_id', true)
    AND environment_id = current_setting('a2.scope_environment_id', true)
  );

CREATE POLICY a2_artifact_revocation_scope ON a2_artifact_reference_revocations
  USING (
    organization_id = current_setting('a2.scope_organization_id', true)
    AND tenant_id = current_setting('a2.scope_tenant_id', true)
    AND workspace_id = current_setting('a2.scope_workspace_id', true)
    AND project_id = current_setting('a2.scope_project_id', true)
    AND environment_id = current_setting('a2.scope_environment_id', true)
  )
  WITH CHECK (
    organization_id = current_setting('a2.scope_organization_id', true)
    AND tenant_id = current_setting('a2.scope_tenant_id', true)
    AND workspace_id = current_setting('a2.scope_workspace_id', true)
    AND project_id = current_setting('a2.scope_project_id', true)
    AND environment_id = current_setting('a2.scope_environment_id', true)
  );
