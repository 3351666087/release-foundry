-- A1 large-SaaS Postgres foundation.
-- This migration defines tenant-scoped control-plane objects, execution/evidence
-- storage, idempotency helpers, usage rollups, and audit-chain tail helpers.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS organizations (
  id UUID PRIMARY KEY,
  slug TEXT NOT NULL,
  display_name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'deleted')),
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ,
  CONSTRAINT organizations_slug_key UNIQUE (slug)
);

CREATE TABLE IF NOT EXISTS workspaces (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  slug TEXT NOT NULL,
  display_name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived', 'deleted')),
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ,
  CONSTRAINT workspaces_org_id_id_key UNIQUE (organization_id, id),
  CONSTRAINT workspaces_org_slug_key UNIQUE (organization_id, slug)
);

CREATE TABLE IF NOT EXISTS projects (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  workspace_id UUID NOT NULL,
  slug TEXT NOT NULL,
  display_name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived', 'deleted')),
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ,
  CONSTRAINT projects_org_id_id_key UNIQUE (organization_id, id),
  CONSTRAINT projects_org_workspace_slug_key UNIQUE (organization_id, workspace_id, slug),
  CONSTRAINT projects_workspace_scope_fk FOREIGN KEY (organization_id, workspace_id)
    REFERENCES workspaces(organization_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS environments (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'production' CHECK (kind IN ('development', 'staging', 'production', 'sandbox')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'deleted')),
  config JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ,
  CONSTRAINT environments_org_id_id_key UNIQUE (organization_id, id),
  CONSTRAINT environments_org_project_name_key UNIQUE (organization_id, project_id, name),
  CONSTRAINT environments_org_project_fk FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS datasets (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  environment_id UUID,
  external_id TEXT,
  name TEXT NOT NULL,
  version TEXT NOT NULL DEFAULT 'latest',
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived', 'deleted')),
  schema_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ,
  CONSTRAINT datasets_org_project_id_key UNIQUE (organization_id, project_id, id),
  CONSTRAINT datasets_org_project_name_version_key UNIQUE (organization_id, project_id, name, version),
  CONSTRAINT datasets_org_project_fk FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT datasets_environment_scope_fk FOREIGN KEY (organization_id, environment_id)
    REFERENCES environments(organization_id, id) ON DELETE SET NULL (environment_id)
);

CREATE TABLE IF NOT EXISTS runs (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  environment_id UUID,
  dataset_id UUID,
  external_id TEXT,
  run_key TEXT,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'canceled')),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  request_fingerprint TEXT,
  summary JSONB NOT NULL DEFAULT '{}'::JSONB,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT runs_org_project_id_key UNIQUE (organization_id, project_id, id),
  CONSTRAINT runs_org_project_run_key_key UNIQUE (organization_id, project_id, run_key),
  CONSTRAINT runs_org_project_fk FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT runs_dataset_scope_fk FOREIGN KEY (organization_id, project_id, dataset_id)
    REFERENCES datasets(organization_id, project_id, id) ON DELETE SET NULL (dataset_id),
  CONSTRAINT runs_environment_scope_fk FOREIGN KEY (organization_id, environment_id)
    REFERENCES environments(organization_id, id) ON DELETE SET NULL (environment_id)
);

CREATE TABLE IF NOT EXISTS case_results (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  run_id UUID NOT NULL,
  dataset_id UUID,
  case_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('passed', 'failed', 'skipped', 'error')),
  score DOUBLE PRECISION,
  failure_class TEXT,
  input JSONB NOT NULL DEFAULT '{}'::JSONB,
  output JSONB NOT NULL DEFAULT '{}'::JSONB,
  evaluation JSONB NOT NULL DEFAULT '{}'::JSONB,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT case_results_org_project_id_key UNIQUE (organization_id, project_id, id),
  CONSTRAINT case_results_org_project_run_case_key UNIQUE (organization_id, project_id, run_id, case_id),
  CONSTRAINT case_results_run_scope_fk FOREIGN KEY (organization_id, project_id, run_id)
    REFERENCES runs(organization_id, project_id, id) ON DELETE CASCADE,
  CONSTRAINT case_results_dataset_scope_fk FOREIGN KEY (organization_id, project_id, dataset_id)
    REFERENCES datasets(organization_id, project_id, id) ON DELETE SET NULL (dataset_id)
);

CREATE TABLE IF NOT EXISTS trace_events (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  run_id UUID NOT NULL,
  case_result_id UUID,
  parent_event_id UUID,
  event_type TEXT NOT NULL,
  span_id TEXT,
  sequence_no BIGINT NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  attributes JSONB NOT NULL DEFAULT '{}'::JSONB,
  payload JSONB NOT NULL DEFAULT '{}'::JSONB,
  CONSTRAINT trace_events_org_project_id_key UNIQUE (organization_id, project_id, id),
  CONSTRAINT trace_events_org_project_run_seq_key UNIQUE (organization_id, project_id, run_id, sequence_no),
  CONSTRAINT trace_events_run_scope_fk FOREIGN KEY (organization_id, project_id, run_id)
    REFERENCES runs(organization_id, project_id, id) ON DELETE CASCADE,
  CONSTRAINT trace_events_case_scope_fk FOREIGN KEY (organization_id, project_id, case_result_id)
    REFERENCES case_results(organization_id, project_id, id) ON DELETE SET NULL (case_result_id),
  CONSTRAINT trace_events_parent_scope_fk FOREIGN KEY (organization_id, project_id, parent_event_id)
    REFERENCES trace_events(organization_id, project_id, id) ON DELETE SET NULL (parent_event_id)
);

CREATE TABLE IF NOT EXISTS observations (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  run_id UUID,
  case_result_id UUID,
  trace_event_id UUID,
  observation_type TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('debug', 'info', 'warning', 'error', 'critical')),
  subject_type TEXT,
  subject_id TEXT,
  value JSONB NOT NULL DEFAULT '{}'::JSONB,
  observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT observations_run_scope_fk FOREIGN KEY (organization_id, project_id, run_id)
    REFERENCES runs(organization_id, project_id, id) ON DELETE CASCADE,
  CONSTRAINT observations_case_scope_fk FOREIGN KEY (organization_id, project_id, case_result_id)
    REFERENCES case_results(organization_id, project_id, id) ON DELETE SET NULL (case_result_id),
  CONSTRAINT observations_trace_event_scope_fk FOREIGN KEY (organization_id, project_id, trace_event_id)
    REFERENCES trace_events(organization_id, project_id, id) ON DELETE SET NULL (trace_event_id)
);

CREATE TABLE IF NOT EXISTS artifacts (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  run_id UUID,
  case_result_id UUID,
  artifact_type TEXT NOT NULL,
  storage_uri TEXT NOT NULL,
  content_type TEXT,
  byte_size BIGINT,
  sha256 TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT artifacts_org_project_sha_key UNIQUE (organization_id, project_id, sha256),
  CONSTRAINT artifacts_run_scope_fk FOREIGN KEY (organization_id, project_id, run_id)
    REFERENCES runs(organization_id, project_id, id) ON DELETE CASCADE,
  CONSTRAINT artifacts_case_scope_fk FOREIGN KEY (organization_id, project_id, case_result_id)
    REFERENCES case_results(organization_id, project_id, id) ON DELETE SET NULL (case_result_id)
);

CREATE TABLE IF NOT EXISTS evidence_bundles (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  run_id UUID,
  case_result_id UUID,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'sealed', 'deleted')),
  manifest JSONB NOT NULL DEFAULT '{}'::JSONB,
  artifact_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
  sealed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT evidence_bundles_org_project_name_key UNIQUE (organization_id, project_id, name),
  CONSTRAINT evidence_bundles_run_scope_fk FOREIGN KEY (organization_id, project_id, run_id)
    REFERENCES runs(organization_id, project_id, id) ON DELETE SET NULL (run_id),
  CONSTRAINT evidence_bundles_case_scope_fk FOREIGN KEY (organization_id, project_id, case_result_id)
    REFERENCES case_results(organization_id, project_id, id) ON DELETE SET NULL (case_result_id)
);

CREATE TABLE IF NOT EXISTS api_keys (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  workspace_id UUID,
  project_id UUID NOT NULL,
  name TEXT NOT NULL,
  key_prefix TEXT NOT NULL,
  key_hash TEXT NOT NULL,
  scopes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked', 'expired')),
  expires_at TIMESTAMPTZ,
  last_used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at TIMESTAMPTZ,
  CONSTRAINT api_keys_hash_key UNIQUE (key_hash),
  CONSTRAINT api_keys_org_prefix_key UNIQUE (organization_id, key_prefix),
  CONSTRAINT api_keys_workspace_scope_fk FOREIGN KEY (organization_id, workspace_id)
    REFERENCES workspaces(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT api_keys_project_scope_fk FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS webhook_endpoints (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  url TEXT NOT NULL,
  secret_hash TEXT NOT NULL,
  event_types TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'deleted')),
  retry_policy JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ,
  CONSTRAINT webhook_endpoints_org_url_key UNIQUE (organization_id, url),
  CONSTRAINT webhook_endpoints_project_scope_fk FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  idempotency_key TEXT NOT NULL,
  request_method TEXT NOT NULL,
  request_path TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'succeeded', 'failed')),
  response_code INTEGER,
  response_body JSONB,
  locked_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT idempotency_keys_org_project_id_key UNIQUE (organization_id, project_id, id),
  CONSTRAINT idempotency_keys_org_project_key_unique UNIQUE (organization_id, project_id, idempotency_key),
  CONSTRAINT idempotency_keys_scope_fingerprint_unique UNIQUE (organization_id, project_id, request_method, request_path, fingerprint),
  CONSTRAINT idempotency_keys_project_scope_fk FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS usage_ledger (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  workspace_id UUID,
  project_id UUID NOT NULL,
  environment_id UUID,
  idempotency_key_id UUID,
  meter TEXT NOT NULL,
  quantity NUMERIC(20, 6) NOT NULL CHECK (quantity >= 0),
  unit TEXT NOT NULL DEFAULT 'count',
  source_type TEXT NOT NULL,
  source_id TEXT,
  period_start TIMESTAMPTZ NOT NULL,
  period_end TIMESTAMPTZ NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT usage_ledger_period_check CHECK (period_end > period_start),
  CONSTRAINT usage_ledger_meter_check CHECK (meter IN ('runs', 'observations', 'media', 'voice_minutes', 'projects', 'storage_bytes')),
  CONSTRAINT usage_ledger_idempotency_scope_fk FOREIGN KEY (organization_id, project_id, idempotency_key_id)
    REFERENCES idempotency_keys(organization_id, project_id, id) ON DELETE SET NULL (idempotency_key_id),
  CONSTRAINT usage_ledger_workspace_scope_fk FOREIGN KEY (organization_id, workspace_id)
    REFERENCES workspaces(organization_id, id) ON DELETE SET NULL (workspace_id),
  CONSTRAINT usage_ledger_project_scope_fk FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT usage_ledger_environment_scope_fk FOREIGN KEY (organization_id, environment_id)
    REFERENCES environments(organization_id, id) ON DELETE SET NULL (environment_id)
);

CREATE TABLE IF NOT EXISTS usage_rollups (
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  workspace_id UUID,
  project_id UUID NOT NULL,
  meter TEXT NOT NULL,
  period TEXT NOT NULL CHECK (period IN ('hour', 'day', 'month')),
  period_start TIMESTAMPTZ NOT NULL,
  period_end TIMESTAMPTZ NOT NULL,
  total_quantity NUMERIC(20, 6) NOT NULL DEFAULT 0 CHECK (total_quantity >= 0),
  ledger_entries BIGINT NOT NULL DEFAULT 0 CHECK (ledger_entries >= 0),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, project_id, meter, period, period_start),
  CONSTRAINT usage_rollups_meter_check CHECK (meter IN ('runs', 'observations', 'media', 'voice_minutes', 'projects', 'storage_bytes')),
  CONSTRAINT usage_rollups_period_bounds_check CHECK (period_end > period_start),
  CONSTRAINT usage_rollups_workspace_scope_fk FOREIGN KEY (organization_id, workspace_id)
    REFERENCES workspaces(organization_id, id) ON DELETE SET NULL (workspace_id),
  CONSTRAINT usage_rollups_project_scope_fk FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS quota_policies (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  meter TEXT NOT NULL,
  period TEXT NOT NULL CHECK (period IN ('hour', 'day', 'month')),
  limit_quantity NUMERIC(20, 6) NOT NULL CHECK (limit_quantity >= 0),
  enforcement_mode TEXT NOT NULL DEFAULT 'soft' CHECK (enforcement_mode IN ('soft', 'hard')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'deleted')),
  effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
  effective_until TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT quota_policies_meter_check CHECK (meter IN ('runs', 'observations', 'media', 'voice_minutes', 'projects', 'storage_bytes')),
  CONSTRAINT quota_policies_org_project_meter_period_key UNIQUE (organization_id, project_id, meter, period),
  CONSTRAINT quota_policies_project_scope_fk FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS jobs (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  environment_id UUID,
  job_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'canceled', 'dead_letter')),
  priority INTEGER NOT NULL DEFAULT 100,
  dedupe_key TEXT,
  run_after TIMESTAMPTZ NOT NULL DEFAULT now(),
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  payload JSONB NOT NULL DEFAULT '{}'::JSONB,
  locked_by TEXT,
  locked_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT jobs_org_project_dedupe_key UNIQUE (organization_id, project_id, job_type, dedupe_key),
  CONSTRAINT jobs_project_scope_fk FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT jobs_environment_scope_fk FOREIGN KEY (organization_id, environment_id)
    REFERENCES environments(organization_id, id) ON DELETE SET NULL (environment_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id UUID NOT NULL,
  actor_type TEXT NOT NULL,
  actor_id TEXT,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT,
  request_id TEXT,
  idempotency_key_id UUID,
  payload JSONB NOT NULL DEFAULT '{}'::JSONB,
  prev_hash TEXT,
  entry_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT audit_log_entry_hash_key UNIQUE (entry_hash),
  CONSTRAINT audit_log_idempotency_scope_fk FOREIGN KEY (organization_id, project_id, idempotency_key_id)
    REFERENCES idempotency_keys(organization_id, project_id, id) ON DELETE SET NULL (idempotency_key_id),
  CONSTRAINT audit_log_project_scope_fk FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_organizations_status ON organizations(status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_workspaces_org_status ON workspaces(organization_id, status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_projects_org_workspace_status ON projects(organization_id, workspace_id, status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_environments_project_kind ON environments(organization_id, project_id, kind) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_datasets_project_created ON datasets(organization_id, project_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_runs_project_created ON runs(organization_id, project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_project_status ON runs(organization_id, project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_case_results_run_status ON case_results(organization_id, project_id, run_id, status);
CREATE INDEX IF NOT EXISTS idx_trace_events_run_order ON trace_events(organization_id, project_id, run_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_observations_project_type_time ON observations(organization_id, project_id, observation_type, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_artifacts_project_type_created ON artifacts(organization_id, project_id, artifact_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_bundles_project_status ON evidence_bundles(organization_id, project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_api_keys_org_status ON api_keys(organization_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_webhook_endpoints_org_status ON webhook_endpoints(organization_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_idempotency_keys_created ON idempotency_keys(organization_id, project_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_ledger_idempotency_key_unique
  ON usage_ledger(organization_id, project_id, idempotency_key_id)
  WHERE idempotency_key_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_usage_ledger_scope_meter_period ON usage_ledger(organization_id, project_id, meter, period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_usage_ledger_workspace_meter_period ON usage_ledger(organization_id, workspace_id, meter, period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_usage_rollups_scope_meter_period ON usage_rollups(organization_id, project_id, meter, period, period_start DESC);
CREATE INDEX IF NOT EXISTS idx_usage_rollups_workspace_meter_period ON usage_rollups(organization_id, workspace_id, meter, period, period_start DESC);
CREATE INDEX IF NOT EXISTS idx_quota_policies_scope_meter ON quota_policies(organization_id, project_id, meter, status);
CREATE INDEX IF NOT EXISTS idx_jobs_ready_queue ON jobs(status, run_after, priority, created_at) WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS idx_jobs_project_status ON jobs(organization_id, project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_scope_created ON audit_log(organization_id, project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource ON audit_log(organization_id, resource_type, resource_id, created_at DESC);

CREATE OR REPLACE FUNCTION a1_current_organization_id()
RETURNS UUID
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('app.a1_organization_id', TRUE), '')::UUID;
$$;

ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE environments ENABLE ROW LEVEL SECURITY;
ALTER TABLE datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE case_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_bundles ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_endpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE idempotency_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_rollups ENABLE ROW LEVEL SECURITY;
ALTER TABLE quota_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

ALTER TABLE organizations FORCE ROW LEVEL SECURITY;
ALTER TABLE workspaces FORCE ROW LEVEL SECURITY;
ALTER TABLE projects FORCE ROW LEVEL SECURITY;
ALTER TABLE environments FORCE ROW LEVEL SECURITY;
ALTER TABLE datasets FORCE ROW LEVEL SECURITY;
ALTER TABLE runs FORCE ROW LEVEL SECURITY;
ALTER TABLE case_results FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_events FORCE ROW LEVEL SECURITY;
ALTER TABLE observations FORCE ROW LEVEL SECURITY;
ALTER TABLE artifacts FORCE ROW LEVEL SECURITY;
ALTER TABLE evidence_bundles FORCE ROW LEVEL SECURITY;
ALTER TABLE api_keys FORCE ROW LEVEL SECURITY;
ALTER TABLE webhook_endpoints FORCE ROW LEVEL SECURITY;
ALTER TABLE idempotency_keys FORCE ROW LEVEL SECURITY;
ALTER TABLE usage_ledger FORCE ROW LEVEL SECURITY;
ALTER TABLE usage_rollups FORCE ROW LEVEL SECURITY;
ALTER TABLE quota_policies FORCE ROW LEVEL SECURITY;
ALTER TABLE jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS organizations_organization_isolation ON organizations;
DROP POLICY IF EXISTS workspaces_organization_isolation ON workspaces;
DROP POLICY IF EXISTS projects_organization_isolation ON projects;
DROP POLICY IF EXISTS environments_organization_isolation ON environments;
DROP POLICY IF EXISTS datasets_organization_isolation ON datasets;
DROP POLICY IF EXISTS runs_organization_isolation ON runs;
DROP POLICY IF EXISTS case_results_organization_isolation ON case_results;
DROP POLICY IF EXISTS trace_events_organization_isolation ON trace_events;
DROP POLICY IF EXISTS observations_organization_isolation ON observations;
DROP POLICY IF EXISTS artifacts_organization_isolation ON artifacts;
DROP POLICY IF EXISTS evidence_bundles_organization_isolation ON evidence_bundles;
DROP POLICY IF EXISTS api_keys_organization_isolation ON api_keys;
DROP POLICY IF EXISTS webhook_endpoints_organization_isolation ON webhook_endpoints;
DROP POLICY IF EXISTS idempotency_keys_organization_isolation ON idempotency_keys;
DROP POLICY IF EXISTS usage_ledger_organization_isolation ON usage_ledger;
DROP POLICY IF EXISTS usage_rollups_organization_isolation ON usage_rollups;
DROP POLICY IF EXISTS quota_policies_organization_isolation ON quota_policies;
DROP POLICY IF EXISTS jobs_organization_isolation ON jobs;
DROP POLICY IF EXISTS audit_log_organization_isolation ON audit_log;

CREATE POLICY organizations_organization_isolation ON organizations
  USING (id = a1_current_organization_id())
  WITH CHECK (id = a1_current_organization_id());

CREATE POLICY workspaces_organization_isolation ON workspaces
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY projects_organization_isolation ON projects
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY environments_organization_isolation ON environments
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY datasets_organization_isolation ON datasets
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY runs_organization_isolation ON runs
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY case_results_organization_isolation ON case_results
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY trace_events_organization_isolation ON trace_events
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY observations_organization_isolation ON observations
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY artifacts_organization_isolation ON artifacts
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY evidence_bundles_organization_isolation ON evidence_bundles
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY api_keys_organization_isolation ON api_keys
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY webhook_endpoints_organization_isolation ON webhook_endpoints
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY idempotency_keys_organization_isolation ON idempotency_keys
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY usage_ledger_organization_isolation ON usage_ledger
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY usage_rollups_organization_isolation ON usage_rollups
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY quota_policies_organization_isolation ON quota_policies
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY jobs_organization_isolation ON jobs
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY audit_log_organization_isolation ON audit_log
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE OR REPLACE FUNCTION ensure_idempotency_fingerprint(
  p_organization_id UUID,
  p_project_id UUID,
  p_idempotency_key TEXT,
  p_request_method TEXT,
  p_request_path TEXT,
  p_fingerprint TEXT,
  p_id UUID DEFAULT NULL
)
RETURNS idempotency_keys
LANGUAGE plpgsql
AS $$
DECLARE
  existing_record idempotency_keys%ROWTYPE;
  inserted_record idempotency_keys%ROWTYPE;
BEGIN
  SELECT *
    INTO existing_record
    FROM idempotency_keys
   WHERE organization_id = p_organization_id
     AND project_id IS NOT DISTINCT FROM p_project_id
     AND idempotency_key = p_idempotency_key
   FOR UPDATE;

  IF FOUND THEN
    IF existing_record.fingerprint <> p_fingerprint
       OR existing_record.request_method <> p_request_method
       OR existing_record.request_path <> p_request_path THEN
      RAISE EXCEPTION 'idempotency key conflict for organization %, project %, key %',
        p_organization_id, p_project_id, p_idempotency_key
        USING ERRCODE = '23505', CONSTRAINT = 'idempotency_keys_org_project_key_unique';
    END IF;
    RETURN existing_record;
  END IF;

  INSERT INTO idempotency_keys (
    id,
    organization_id,
    project_id,
    idempotency_key,
    request_method,
    request_path,
    fingerprint
  ) VALUES (
    COALESCE(p_id, gen_random_uuid()),
    p_organization_id,
    p_project_id,
    p_idempotency_key,
    p_request_method,
    p_request_path,
    p_fingerprint
  )
  RETURNING * INTO inserted_record;

  RETURN inserted_record;
EXCEPTION
  WHEN unique_violation THEN
    SELECT *
      INTO existing_record
      FROM idempotency_keys
     WHERE organization_id = p_organization_id
       AND project_id IS NOT DISTINCT FROM p_project_id
       AND idempotency_key = p_idempotency_key
     FOR UPDATE;

    IF FOUND
       AND existing_record.fingerprint = p_fingerprint
       AND existing_record.request_method = p_request_method
       AND existing_record.request_path = p_request_path THEN
      RETURN existing_record;
    END IF;

    RAISE EXCEPTION 'idempotency fingerprint conflict for organization %, project %, key %',
      p_organization_id, p_project_id, p_idempotency_key
      USING ERRCODE = '23505', CONSTRAINT = 'idempotency_keys_scope_fingerprint_unique';
END;
$$;

CREATE OR REPLACE FUNCTION rollup_usage(
  p_organization_id UUID,
  p_project_id UUID,
  p_meter TEXT,
  p_period_start TIMESTAMPTZ,
  p_period_end TIMESTAMPTZ
)
RETURNS TABLE (
  organization_id UUID,
  project_id UUID,
  meter TEXT,
  total_quantity NUMERIC,
  ledger_entries BIGINT,
  period_start TIMESTAMPTZ,
  period_end TIMESTAMPTZ
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
  RETURN QUERY
  SELECT
    u.organization_id,
    u.project_id,
    u.meter,
    COALESCE(SUM(u.quantity), 0)::NUMERIC AS total_quantity,
    COUNT(*)::BIGINT AS ledger_entries,
    p_period_start AS period_start,
    p_period_end AS period_end
  FROM usage_ledger u
  WHERE u.organization_id = p_organization_id
    AND u.project_id IS NOT DISTINCT FROM p_project_id
    AND u.meter = p_meter
    AND u.period_start >= p_period_start
    AND u.period_end <= p_period_end
  GROUP BY u.organization_id, u.project_id, u.meter;
END;
$$;

CREATE OR REPLACE FUNCTION usage_rollup_period_bounds(
  p_period TEXT,
  p_at TIMESTAMPTZ
)
RETURNS TABLE (
  period_start TIMESTAMPTZ,
  period_end TIMESTAMPTZ
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
  IF p_period = 'hour' THEN
    period_start := date_trunc('hour', p_at);
    period_end := period_start + INTERVAL '1 hour';
  ELSIF p_period = 'day' THEN
    period_start := date_trunc('day', p_at);
    period_end := period_start + INTERVAL '1 day';
  ELSIF p_period = 'month' THEN
    period_start := date_trunc('month', p_at);
    period_end := period_start + INTERVAL '1 month';
  ELSE
    RAISE EXCEPTION 'unsupported usage rollup period: %', p_period USING ERRCODE = '22023';
  END IF;

  RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION upsert_usage_rollup_from_ledger()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  bounds RECORD;
  rollup_period TEXT;
BEGIN
  FOREACH rollup_period IN ARRAY ARRAY['hour', 'day', 'month'] LOOP
    SELECT period_start, period_end
      INTO bounds
      FROM usage_rollup_period_bounds(rollup_period, NEW.period_start);

    INSERT INTO usage_rollups (
      organization_id,
      workspace_id,
      project_id,
      meter,
      period,
      period_start,
      period_end,
      total_quantity,
      ledger_entries,
      updated_at
    )
    VALUES (
      NEW.organization_id,
      NEW.workspace_id,
      NEW.project_id,
      NEW.meter,
      rollup_period,
      bounds.period_start,
      bounds.period_end,
      NEW.quantity,
      1,
      now()
    )
    ON CONFLICT (organization_id, project_id, meter, period, period_start)
    DO UPDATE SET
      workspace_id = COALESCE(usage_rollups.workspace_id, EXCLUDED.workspace_id),
      period_end = EXCLUDED.period_end,
      total_quantity = usage_rollups.total_quantity + EXCLUDED.total_quantity,
      ledger_entries = usage_rollups.ledger_entries + 1,
      updated_at = now();
  END LOOP;

  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION audit_quota_policy_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  target_policy quota_policies%ROWTYPE;
  previous_hash TEXT;
  audit_payload JSONB;
BEGIN
  target_policy := COALESCE(NEW, OLD);

  SELECT audit_chain_tail(target_policy.organization_id, target_policy.project_id)
    INTO previous_hash;

  audit_payload := jsonb_build_object(
    'meter', target_policy.meter,
    'period', target_policy.period,
    'limit_quantity', target_policy.limit_quantity,
    'enforcement_mode', target_policy.enforcement_mode,
    'status', target_policy.status
  );

  INSERT INTO audit_log (
    id,
    organization_id,
    project_id,
    actor_type,
    actor_id,
    action,
    resource_type,
    resource_id,
    payload,
    prev_hash,
    entry_hash,
    created_at
  )
  VALUES (
    gen_random_uuid(),
    target_policy.organization_id,
    target_policy.project_id,
    'system',
    'quota_policy_trigger',
    'quota_policy.' || lower(TG_OP),
    'quota_policy',
    target_policy.id::TEXT,
    audit_payload,
    previous_hash,
    encode(digest(COALESCE(previous_hash, '') || target_policy.id::TEXT || TG_OP || audit_payload::TEXT || now()::TEXT, 'sha256'), 'hex'),
    now()
  );

  RETURN target_policy;
END;
$$;

DROP TRIGGER IF EXISTS usage_ledger_rollup_after_insert ON usage_ledger;
CREATE TRIGGER usage_ledger_rollup_after_insert
AFTER INSERT ON usage_ledger
FOR EACH ROW
EXECUTE FUNCTION upsert_usage_rollup_from_ledger();

DROP TRIGGER IF EXISTS quota_policies_audit_after_change ON quota_policies;
CREATE TRIGGER quota_policies_audit_after_change
AFTER INSERT OR UPDATE OR DELETE ON quota_policies
FOR EACH ROW
EXECUTE FUNCTION audit_quota_policy_change();

CREATE OR REPLACE FUNCTION audit_chain_tail(
  p_organization_id UUID,
  p_project_id UUID DEFAULT NULL
)
RETURNS TEXT
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  tail_hash TEXT;
BEGIN
  SELECT entry_hash
    INTO tail_hash
    FROM audit_log
   WHERE organization_id = p_organization_id
     AND (p_project_id IS NULL OR project_id IS NOT DISTINCT FROM p_project_id)
   ORDER BY created_at DESC, id DESC
   LIMIT 1;

  RETURN tail_hash;
END;
$$;

COMMIT;
