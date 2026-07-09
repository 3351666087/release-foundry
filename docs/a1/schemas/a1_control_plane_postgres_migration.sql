-- A1 control-plane Postgres migration artifact.
-- Source of truth: packages/go/ashrclone/postgres.go PostgresSchemaSQL first slice.
-- Scope: tenants, projects, datasets, runs, idempotency ledger, tenant RLS, and updated_at audit triggers.

BEGIN;

CREATE OR REPLACE FUNCTION ashr_current_tenant_id()
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT NULLIF(current_setting('app.tenant_id', true), '')
$$;

CREATE OR REPLACE FUNCTION ashr_set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS ashr_tenants (
    tenant_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ashr_projects (
    tenant_id TEXT NOT NULL REFERENCES ashr_tenants(tenant_id) ON DELETE CASCADE,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id)
);

CREATE TABLE IF NOT EXISTS ashr_datasets (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    name TEXT NOT NULL,
    cases JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, dataset_id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES ashr_projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ashr_runs (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    agent_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, run_id),
    FOREIGN KEY (tenant_id, project_id, dataset_id) REFERENCES ashr_datasets(tenant_id, project_id, dataset_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS ashr_idempotency_ledger (
    operation TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    key TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    response_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (operation, tenant_id, project_id, key)
);

CREATE INDEX IF NOT EXISTS ashr_runs_dataset_idx ON ashr_runs (tenant_id, project_id, dataset_id);

CREATE TABLE IF NOT EXISTS ashr_worker_jobs (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    job_type TEXT NOT NULL,
    target_id TEXT NOT NULL DEFAULT '',
    payload_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    lease_owner_id TEXT NOT NULL DEFAULT '',
    lease_expires_at TIMESTAMPTZ,
    available_at TIMESTAMPTZ,
    last_error JSONB,
    result_sha256 TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL DEFAULT '',
    request_id TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    dead_lettered_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, project_id, job_id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES ashr_projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ashr_worker_jobs_lease_idx ON ashr_worker_jobs (tenant_id, project_id, status, job_type, priority, available_at, created_at);
CREATE INDEX IF NOT EXISTS ashr_worker_jobs_status_idx ON ashr_worker_jobs (tenant_id, project_id, status, updated_at);

CREATE TABLE IF NOT EXISTS ashr_run_uploads (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    upload_id TEXT NOT NULL,
    result_sha256 TEXT NOT NULL,
    api_key_id TEXT NOT NULL DEFAULT '',
    request_id TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, run_id, upload_id),
    FOREIGN KEY (tenant_id, project_id, run_id) REFERENCES ashr_runs(tenant_id, project_id, run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ashr_trace_batches (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    observation_count INTEGER NOT NULL DEFAULT 0,
    observations_sha256 TEXT NOT NULL,
    api_key_id TEXT NOT NULL DEFAULT '',
    request_id TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, run_id, batch_id),
    FOREIGN KEY (tenant_id, project_id, run_id) REFERENCES ashr_runs(tenant_id, project_id, run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ashr_artifact_manifests (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL,
    api_key_id TEXT NOT NULL DEFAULT '',
    request_id TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, run_id, artifact_id),
    FOREIGN KEY (tenant_id, project_id, run_id) REFERENCES ashr_runs(tenant_id, project_id, run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ashr_run_uploads_run_idx ON ashr_run_uploads (tenant_id, project_id, run_id, created_at);
CREATE INDEX IF NOT EXISTS ashr_trace_batches_run_idx ON ashr_trace_batches (tenant_id, project_id, run_id, created_at);
CREATE INDEX IF NOT EXISTS ashr_artifact_manifests_run_idx ON ashr_artifact_manifests (tenant_id, project_id, run_id, created_at, artifact_id);

CREATE TABLE IF NOT EXISTS ashr_quota_ledger (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    usage_event_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    units INTEGER NOT NULL DEFAULT 1,
    api_key_id TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL DEFAULT '',
    request_id TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    target_id TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, usage_event_id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES ashr_projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ashr_audit_events (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    audit_event_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_id TEXT NOT NULL DEFAULT '',
    api_key_id TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL DEFAULT '',
    request_id TEXT NOT NULL DEFAULT '',
    previous_hash TEXT NOT NULL DEFAULT '',
    event_hash TEXT NOT NULL,
    after_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, audit_event_id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES ashr_projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ashr_quota_ledger_scope_idx ON ashr_quota_ledger (tenant_id, project_id, operation, created_at);
CREATE INDEX IF NOT EXISTS ashr_quota_ledger_run_idx ON ashr_quota_ledger (tenant_id, project_id, run_id, created_at);
CREATE INDEX IF NOT EXISTS ashr_audit_events_scope_idx ON ashr_audit_events (tenant_id, project_id, action, created_at);
CREATE INDEX IF NOT EXISTS ashr_audit_events_target_idx ON ashr_audit_events (tenant_id, project_id, target_id, created_at);

DROP TRIGGER IF EXISTS ashr_tenants_set_updated_at ON ashr_tenants;
CREATE TRIGGER ashr_tenants_set_updated_at
BEFORE UPDATE ON ashr_tenants
FOR EACH ROW
EXECUTE FUNCTION ashr_set_updated_at();

DROP TRIGGER IF EXISTS ashr_projects_set_updated_at ON ashr_projects;
CREATE TRIGGER ashr_projects_set_updated_at
BEFORE UPDATE ON ashr_projects
FOR EACH ROW
EXECUTE FUNCTION ashr_set_updated_at();

DROP TRIGGER IF EXISTS ashr_datasets_set_updated_at ON ashr_datasets;
CREATE TRIGGER ashr_datasets_set_updated_at
BEFORE UPDATE ON ashr_datasets
FOR EACH ROW
EXECUTE FUNCTION ashr_set_updated_at();

DROP TRIGGER IF EXISTS ashr_runs_set_updated_at ON ashr_runs;
CREATE TRIGGER ashr_runs_set_updated_at
BEFORE UPDATE ON ashr_runs
FOR EACH ROW
EXECUTE FUNCTION ashr_set_updated_at();

ALTER TABLE ashr_tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_datasets ENABLE ROW LEVEL SECURITY;
DROP TRIGGER IF EXISTS ashr_worker_jobs_set_updated_at ON ashr_worker_jobs;
CREATE TRIGGER ashr_worker_jobs_set_updated_at
BEFORE UPDATE ON ashr_worker_jobs
FOR EACH ROW
EXECUTE FUNCTION ashr_set_updated_at();

ALTER TABLE ashr_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_idempotency_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_worker_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_run_uploads ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_trace_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_artifact_manifests ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_quota_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_audit_events ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'ashr_tenants' AND policyname = 'ashr_tenants_tenant_isolation') THEN
        CREATE POLICY ashr_tenants_tenant_isolation ON ashr_tenants
        USING (tenant_id = ashr_current_tenant_id())
        WITH CHECK (tenant_id = ashr_current_tenant_id());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'ashr_projects' AND policyname = 'ashr_projects_tenant_isolation') THEN
        CREATE POLICY ashr_projects_tenant_isolation ON ashr_projects
        USING (tenant_id = ashr_current_tenant_id())
        WITH CHECK (tenant_id = ashr_current_tenant_id());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'ashr_datasets' AND policyname = 'ashr_datasets_tenant_isolation') THEN
        CREATE POLICY ashr_datasets_tenant_isolation ON ashr_datasets
        USING (tenant_id = ashr_current_tenant_id())
        WITH CHECK (tenant_id = ashr_current_tenant_id());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'ashr_runs' AND policyname = 'ashr_runs_tenant_isolation') THEN
        CREATE POLICY ashr_runs_tenant_isolation ON ashr_runs
        USING (tenant_id = ashr_current_tenant_id())
        WITH CHECK (tenant_id = ashr_current_tenant_id());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'ashr_idempotency_ledger' AND policyname = 'ashr_idempotency_ledger_tenant_isolation') THEN
        CREATE POLICY ashr_idempotency_ledger_tenant_isolation ON ashr_idempotency_ledger
        USING (tenant_id = ashr_current_tenant_id())
        WITH CHECK (tenant_id = ashr_current_tenant_id());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'ashr_worker_jobs' AND policyname = 'ashr_worker_jobs_tenant_isolation') THEN
        CREATE POLICY ashr_worker_jobs_tenant_isolation ON ashr_worker_jobs
        USING (tenant_id = ashr_current_tenant_id())
        WITH CHECK (tenant_id = ashr_current_tenant_id());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'ashr_run_uploads' AND policyname = 'ashr_run_uploads_tenant_isolation') THEN
        CREATE POLICY ashr_run_uploads_tenant_isolation ON ashr_run_uploads
        USING (tenant_id = ashr_current_tenant_id())
        WITH CHECK (tenant_id = ashr_current_tenant_id());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'ashr_trace_batches' AND policyname = 'ashr_trace_batches_tenant_isolation') THEN
        CREATE POLICY ashr_trace_batches_tenant_isolation ON ashr_trace_batches
        USING (tenant_id = ashr_current_tenant_id())
        WITH CHECK (tenant_id = ashr_current_tenant_id());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'ashr_artifact_manifests' AND policyname = 'ashr_artifact_manifests_tenant_isolation') THEN
        CREATE POLICY ashr_artifact_manifests_tenant_isolation ON ashr_artifact_manifests
        USING (tenant_id = ashr_current_tenant_id())
        WITH CHECK (tenant_id = ashr_current_tenant_id());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'ashr_quota_ledger' AND policyname = 'ashr_quota_ledger_tenant_isolation') THEN
        CREATE POLICY ashr_quota_ledger_tenant_isolation ON ashr_quota_ledger
        USING (tenant_id = ashr_current_tenant_id())
        WITH CHECK (tenant_id = ashr_current_tenant_id());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'ashr_audit_events' AND policyname = 'ashr_audit_events_tenant_isolation') THEN
        CREATE POLICY ashr_audit_events_tenant_isolation ON ashr_audit_events
        USING (tenant_id = ashr_current_tenant_id())
        WITH CHECK (tenant_id = ashr_current_tenant_id());
    END IF;
END;
$$;

COMMIT;
