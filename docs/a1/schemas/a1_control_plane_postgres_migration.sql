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
ALTER TABLE ashr_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_idempotency_ledger ENABLE ROW LEVEL SECURITY;

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
END;
$$;

COMMIT;
