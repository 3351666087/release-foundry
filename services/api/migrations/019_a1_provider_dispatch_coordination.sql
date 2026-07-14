BEGIN;

CREATE TABLE IF NOT EXISTS ashr_provider_dispatches (
  tenant_id UUID NOT NULL,
  project_id UUID NOT NULL,
  dispatch_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  operation TEXT NOT NULL,
  request_fingerprint TEXT NOT NULL CHECK (length(request_fingerprint)=64),
  status TEXT NOT NULL DEFAULT 'pending' CHECK
    (status IN ('pending','claimed','indeterminate','reconciling','completed','failed','cancelled')),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  fencing_token BIGINT NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
  lease_owner_id TEXT NOT NULL DEFAULT '',
  lease_expires_at TIMESTAMPTZ,
  provider_request_id TEXT NOT NULL DEFAULT '',
  stream_observed BOOLEAN NOT NULL DEFAULT false,
  stream_observed_sha256 TEXT NOT NULL DEFAULT '',
  stream_observed_fencing_token BIGINT,
  stream_observed_at TIMESTAMPTZ,
  terminal_proof_sha256 TEXT NOT NULL DEFAULT '',
  terminal_response_sha256 TEXT NOT NULL DEFAULT '',
  reconciliation_reason TEXT NOT NULL DEFAULT '',
  reconciliation_attempts INTEGER NOT NULL DEFAULT 0 CHECK (reconciliation_attempts >= 0),
  next_reconcile_at TIMESTAMPTZ,
  last_error_sha256 TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  claimed_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  failed_at TIMESTAMPTZ,
  PRIMARY KEY (tenant_id,project_id,dispatch_id),
  FOREIGN KEY (tenant_id,project_id)
    REFERENCES projects(organization_id,id) ON DELETE CASCADE,
  CONSTRAINT ashr_provider_dispatch_lease_shape CHECK (
    (status IN ('claimed','reconciling') AND lease_owner_id<>'' AND lease_expires_at IS NOT NULL)
    OR (status NOT IN ('claimed','reconciling') AND lease_owner_id='' AND lease_expires_at IS NULL)
  ),
  CONSTRAINT ashr_provider_dispatch_terminal_proof CHECK (
    (status='completed' AND length(terminal_proof_sha256)=64
      AND length(terminal_response_sha256)=64 AND completed_at IS NOT NULL
      AND stream_observed=true
      AND stream_observed_fencing_token=fencing_token
      AND stream_observed_sha256=terminal_proof_sha256)
    OR status<>'completed'
  ),
  CONSTRAINT ashr_provider_dispatch_stream_observation CHECK (
    (stream_observed=true AND length(stream_observed_sha256)=64
      AND stream_observed_fencing_token IS NOT NULL AND stream_observed_at IS NOT NULL)
    OR (stream_observed=false AND stream_observed_sha256=''
      AND stream_observed_fencing_token IS NULL AND stream_observed_at IS NULL)
  )
);

CREATE INDEX IF NOT EXISTS ashr_provider_dispatch_claim_idx
  ON ashr_provider_dispatches
    (tenant_id,project_id,status,provider,operation,next_reconcile_at,created_at);
CREATE INDEX IF NOT EXISTS ashr_provider_dispatch_lease_idx
  ON ashr_provider_dispatches
    (tenant_id,project_id,status,lease_expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS ashr_provider_dispatch_provider_request_idx
  ON ashr_provider_dispatches(tenant_id,project_id,provider,provider_request_id)
  WHERE provider_request_id<>'';

ALTER TABLE ashr_provider_dispatches ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_provider_dispatches FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ashr_provider_dispatch_tenant_policy ON ashr_provider_dispatches;
DROP POLICY IF EXISTS ashr_provider_dispatch_scope_policy ON ashr_provider_dispatches;
CREATE POLICY ashr_provider_dispatch_scope_policy ON ashr_provider_dispatches
  USING (
    tenant_id=NULLIF(current_setting('app.a1_organization_id',true),'')::UUID
    AND project_id=NULLIF(current_setting('app.a1_project_id',true),'')::UUID
  )
  WITH CHECK (
    tenant_id=NULLIF(current_setting('app.a1_organization_id',true),'')::UUID
    AND project_id=NULLIF(current_setting('app.a1_project_id',true),'')::UUID
  );

COMMIT;
