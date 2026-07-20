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

CREATE OR REPLACE FUNCTION ashr_current_account_id()
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT NULLIF(current_setting('app.account_id', true), '')
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

CREATE TABLE IF NOT EXISTS ashr_accounts (
    account_id TEXT PRIMARY KEY,
    primary_email_normalized TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    locale TEXT NOT NULL DEFAULT 'zh-CN',
    region TEXT NOT NULL DEFAULT 'cn',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'deleted')),
    two_factor_enabled BOOLEAN NOT NULL DEFAULT false,
    two_factor_methods TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ashr_identity_credentials (
    credential_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES ashr_accounts(account_id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    provider_kind TEXT NOT NULL,
    provider_subject_fingerprint TEXT NOT NULL CHECK (provider_subject_fingerprint ~ '^[0-9a-f]{64}$'),
    provider_union_fingerprint TEXT NOT NULL DEFAULT '' CHECK (provider_union_fingerprint = '' OR provider_union_fingerprint ~ '^[0-9a-f]{64}$'),
    verified_email_normalized TEXT NOT NULL DEFAULT '',
    verified_phone_e164 TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ,
    UNIQUE (provider, provider_subject_fingerprint)
);

CREATE UNIQUE INDEX IF NOT EXISTS ashr_identity_credentials_union_idx
ON ashr_identity_credentials (provider, provider_union_fingerprint)
WHERE provider_union_fingerprint <> '';
CREATE INDEX IF NOT EXISTS ashr_identity_credentials_account_idx
ON ashr_identity_credentials (account_id, provider, created_at);

CREATE TABLE IF NOT EXISTS ashr_identity_challenges (
    challenge_id TEXT PRIMARY KEY,
    purpose TEXT NOT NULL CHECK (purpose IN ('register', 'login', 'mfa', 'bind')),
    account_id TEXT REFERENCES ashr_accounts(account_id) ON DELETE CASCADE,
    delivery_method TEXT NOT NULL,
    delivery_target_fingerprint TEXT NOT NULL CHECK (delivery_target_fingerprint ~ '^[0-9a-f]{64}$'),
    delivery_target_ciphertext BYTEA NOT NULL,
    delivery_target_key_id TEXT NOT NULL,
    secret_hash TEXT NOT NULL CHECK (secret_hash ~ '^[0-9a-f]{64}$'),
    secret_hash_key_id TEXT NOT NULL,
    locale TEXT NOT NULL DEFAULT '',
    region TEXT NOT NULL DEFAULT '',
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ashr_identity_challenges_expiry_idx
ON ashr_identity_challenges (expires_at)
WHERE consumed_at IS NULL;
CREATE INDEX IF NOT EXISTS ashr_identity_challenges_account_idx
ON ashr_identity_challenges (account_id, purpose, created_at);

CREATE TABLE IF NOT EXISTS ashr_identity_sessions (
    session_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES ashr_accounts(account_id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    token_hash_key_id TEXT NOT NULL,
    auth_methods TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ashr_identity_sessions_account_idx
ON ashr_identity_sessions (account_id, created_at);
CREATE INDEX IF NOT EXISTS ashr_identity_sessions_expiry_idx
ON ashr_identity_sessions (expires_at)
WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS ashr_account_organization_memberships (
    account_id TEXT NOT NULL REFERENCES ashr_accounts(account_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL REFERENCES ashr_tenants(tenant_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member', 'viewer')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('invited', 'active', 'suspended')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, tenant_id)
);

CREATE INDEX IF NOT EXISTS ashr_account_organization_memberships_tenant_idx
ON ashr_account_organization_memberships (tenant_id, status, role, account_id);

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

DROP TRIGGER IF EXISTS ashr_worker_jobs_set_updated_at ON ashr_worker_jobs;
CREATE TRIGGER ashr_worker_jobs_set_updated_at
BEFORE UPDATE ON ashr_worker_jobs
FOR EACH ROW
EXECUTE FUNCTION ashr_set_updated_at();

DROP TRIGGER IF EXISTS ashr_accounts_set_updated_at ON ashr_accounts;
CREATE TRIGGER ashr_accounts_set_updated_at
BEFORE UPDATE ON ashr_accounts
FOR EACH ROW
EXECUTE FUNCTION ashr_set_updated_at();

DROP TRIGGER IF EXISTS ashr_account_organization_memberships_set_updated_at ON ashr_account_organization_memberships;
CREATE TRIGGER ashr_account_organization_memberships_set_updated_at
BEFORE UPDATE ON ashr_account_organization_memberships
FOR EACH ROW
EXECUTE FUNCTION ashr_set_updated_at();

ALTER TABLE ashr_tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_idempotency_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_worker_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_run_uploads ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_trace_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_artifact_manifests ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_quota_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_identity_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_identity_challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_identity_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ashr_account_organization_memberships ENABLE ROW LEVEL SECURITY;

-- Identity rows are account-global rather than tenant-global. FORCE prevents a
-- table-owning application role from accidentally bypassing these policies;
-- migrations and the identity writer should use a narrowly scoped BYPASSRLS
-- role. Credential/challenge/session tables deliberately have no end-user
-- policy and therefore remain deny-by-default outside that trusted writer.
ALTER TABLE ashr_accounts FORCE ROW LEVEL SECURITY;
ALTER TABLE ashr_identity_credentials FORCE ROW LEVEL SECURITY;
ALTER TABLE ashr_identity_challenges FORCE ROW LEVEL SECURITY;
ALTER TABLE ashr_identity_sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE ashr_account_organization_memberships FORCE ROW LEVEL SECURITY;

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

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'ashr_accounts' AND policyname = 'ashr_accounts_account_read') THEN
        CREATE POLICY ashr_accounts_account_read ON ashr_accounts
        FOR SELECT
        USING (account_id = ashr_current_account_id());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'ashr_account_organization_memberships' AND policyname = 'ashr_account_organization_memberships_read') THEN
        CREATE POLICY ashr_account_organization_memberships_read ON ashr_account_organization_memberships
        FOR SELECT
        USING (
            account_id = ashr_current_account_id()
            OR tenant_id = ashr_current_tenant_id()
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'ashr_account_organization_memberships' AND policyname = 'ashr_account_organization_memberships_tenant_write') THEN
        CREATE POLICY ashr_account_organization_memberships_tenant_write ON ashr_account_organization_memberships
        FOR ALL
        USING (tenant_id = ashr_current_tenant_id())
        WITH CHECK (tenant_id = ashr_current_tenant_id());
    END IF;
END;
$$;

COMMIT;
