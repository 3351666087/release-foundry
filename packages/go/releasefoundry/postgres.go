package releasefoundry

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/lib/pq"
)

var ErrPostgresRepositoryNotImplemented = errors.New("postgres repository is not implemented yet")

const PostgresSchemaSQL = `
CREATE TABLE IF NOT EXISTS releasefoundry_tenants (
    tenant_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS releasefoundry_projects (
    tenant_id TEXT NOT NULL REFERENCES releasefoundry_tenants(tenant_id) ON DELETE CASCADE,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id)
);

CREATE TABLE IF NOT EXISTS releasefoundry_datasets (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    name TEXT NOT NULL,
    cases JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, dataset_id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES releasefoundry_projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS releasefoundry_runs (
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
    FOREIGN KEY (tenant_id, project_id, dataset_id) REFERENCES releasefoundry_datasets(tenant_id, project_id, dataset_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS releasefoundry_idempotency_ledger (
    operation TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    key TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    response_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (operation, tenant_id, project_id, key)
);

CREATE INDEX IF NOT EXISTS releasefoundry_runs_dataset_idx ON releasefoundry_runs (tenant_id, project_id, dataset_id);

CREATE TABLE IF NOT EXISTS releasefoundry_worker_jobs (
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
    FOREIGN KEY (tenant_id, project_id) REFERENCES releasefoundry_projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS releasefoundry_api_key_rate_limits (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    key_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    limit_units INTEGER NOT NULL,
    used_units INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, key_id, operation)
);

CREATE INDEX IF NOT EXISTS releasefoundry_worker_jobs_lease_idx ON releasefoundry_worker_jobs (tenant_id, project_id, status, job_type, priority, available_at, created_at);
CREATE INDEX IF NOT EXISTS releasefoundry_worker_jobs_status_idx ON releasefoundry_worker_jobs (tenant_id, project_id, status, updated_at);

CREATE TABLE IF NOT EXISTS releasefoundry_run_uploads (
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
    FOREIGN KEY (tenant_id, project_id, run_id) REFERENCES releasefoundry_runs(tenant_id, project_id, run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS releasefoundry_trace_batches (
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
    FOREIGN KEY (tenant_id, project_id, run_id) REFERENCES releasefoundry_runs(tenant_id, project_id, run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS releasefoundry_artifact_manifests (
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
    FOREIGN KEY (tenant_id, project_id, run_id) REFERENCES releasefoundry_runs(tenant_id, project_id, run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS releasefoundry_run_uploads_run_idx ON releasefoundry_run_uploads (tenant_id, project_id, run_id, created_at);
CREATE INDEX IF NOT EXISTS releasefoundry_trace_batches_run_idx ON releasefoundry_trace_batches (tenant_id, project_id, run_id, created_at);
CREATE INDEX IF NOT EXISTS releasefoundry_artifact_manifests_run_idx ON releasefoundry_artifact_manifests (tenant_id, project_id, run_id, created_at, artifact_id);

CREATE TABLE IF NOT EXISTS releasefoundry_quota_ledger (
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
    FOREIGN KEY (tenant_id, project_id) REFERENCES releasefoundry_projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS releasefoundry_audit_events (
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
    FOREIGN KEY (tenant_id, project_id) REFERENCES releasefoundry_projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS releasefoundry_quota_ledger_scope_idx ON releasefoundry_quota_ledger (tenant_id, project_id, operation, created_at);
CREATE INDEX IF NOT EXISTS releasefoundry_quota_ledger_run_idx ON releasefoundry_quota_ledger (tenant_id, project_id, run_id, created_at);
CREATE INDEX IF NOT EXISTS releasefoundry_audit_events_scope_idx ON releasefoundry_audit_events (tenant_id, project_id, action, created_at);
CREATE INDEX IF NOT EXISTS releasefoundry_audit_events_target_idx ON releasefoundry_audit_events (tenant_id, project_id, target_id, created_at);

CREATE TABLE IF NOT EXISTS releasefoundry_accounts (
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

CREATE TABLE IF NOT EXISTS releasefoundry_identity_credentials (
    credential_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES releasefoundry_accounts(account_id) ON DELETE CASCADE,
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

CREATE UNIQUE INDEX IF NOT EXISTS releasefoundry_identity_credentials_union_idx
ON releasefoundry_identity_credentials (provider, provider_union_fingerprint)
WHERE provider_union_fingerprint <> '';
CREATE INDEX IF NOT EXISTS releasefoundry_identity_credentials_account_idx
ON releasefoundry_identity_credentials (account_id, provider, created_at);

CREATE TABLE IF NOT EXISTS releasefoundry_identity_challenges (
    challenge_id TEXT PRIMARY KEY,
    purpose TEXT NOT NULL CHECK (purpose IN ('register', 'login', 'mfa', 'bind')),
    account_id TEXT REFERENCES releasefoundry_accounts(account_id) ON DELETE CASCADE,
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

CREATE INDEX IF NOT EXISTS releasefoundry_identity_challenges_expiry_idx
ON releasefoundry_identity_challenges (expires_at)
WHERE consumed_at IS NULL;
CREATE INDEX IF NOT EXISTS releasefoundry_identity_challenges_account_idx
ON releasefoundry_identity_challenges (account_id, purpose, created_at);

CREATE TABLE IF NOT EXISTS releasefoundry_identity_sessions (
    session_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES releasefoundry_accounts(account_id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    token_hash_key_id TEXT NOT NULL,
    auth_methods TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS releasefoundry_identity_sessions_account_idx
ON releasefoundry_identity_sessions (account_id, created_at);
CREATE INDEX IF NOT EXISTS releasefoundry_identity_sessions_expiry_idx
ON releasefoundry_identity_sessions (expires_at)
WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS releasefoundry_account_organization_memberships (
    account_id TEXT NOT NULL REFERENCES releasefoundry_accounts(account_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL REFERENCES releasefoundry_tenants(tenant_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member', 'viewer')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('invited', 'active', 'suspended')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, tenant_id)
);

CREATE INDEX IF NOT EXISTS releasefoundry_account_organization_memberships_tenant_idx
ON releasefoundry_account_organization_memberships (tenant_id, status, role, account_id);

CREATE TABLE IF NOT EXISTS releasefoundry_usage_quota_policies (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    meter TEXT NOT NULL,
    limit_units INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, operation),
    FOREIGN KEY (tenant_id, project_id) REFERENCES releasefoundry_projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS releasefoundry_usage_quota_policies_scope_idx ON releasefoundry_usage_quota_policies (tenant_id, project_id, operation, status);
CREATE TABLE IF NOT EXISTS releasefoundry_billing_checkout_plans (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    checkout_id TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    billing_cycle TEXT NOT NULL,
    provider TEXT NOT NULL,
    mode TEXT NOT NULL,
    customer_ref TEXT NOT NULL DEFAULT '',
    checkout_url TEXT NOT NULL,
    price JSONB NOT NULL DEFAULT '{}'::jsonb,
    provider_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    success_url TEXT NOT NULL DEFAULT '',
    cancel_url TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL DEFAULT '',
    request_id TEXT NOT NULL DEFAULT '',
    api_key_id TEXT NOT NULL DEFAULT '',
    provider_called BOOLEAN NOT NULL DEFAULT false,
    real_charge_possible BOOLEAN NOT NULL DEFAULT false,
    raw_payload_included BOOLEAN NOT NULL DEFAULT false,
    raw_secrets_included BOOLEAN NOT NULL DEFAULT false,
    secret_value_present BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, checkout_id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES releasefoundry_projects(tenant_id, project_id) ON DELETE CASCADE,
    CONSTRAINT releasefoundry_billing_checkout_public_safe CHECK (
        provider_called = false AND real_charge_possible = false AND raw_payload_included = false AND raw_secrets_included = false AND secret_value_present = false
    )
);

CREATE TABLE IF NOT EXISTS releasefoundry_billing_portal_plans (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    portal_session_id TEXT NOT NULL,
    plan_id TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL,
    mode TEXT NOT NULL,
    customer_ref TEXT NOT NULL DEFAULT '',
    portal_url TEXT NOT NULL,
    provider_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    return_url TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL DEFAULT '',
    request_id TEXT NOT NULL DEFAULT '',
    api_key_id TEXT NOT NULL DEFAULT '',
    provider_called BOOLEAN NOT NULL DEFAULT false,
    real_charge_possible BOOLEAN NOT NULL DEFAULT false,
    raw_payload_included BOOLEAN NOT NULL DEFAULT false,
    raw_secrets_included BOOLEAN NOT NULL DEFAULT false,
    secret_value_present BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, portal_session_id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES releasefoundry_projects(tenant_id, project_id) ON DELETE CASCADE,
    CONSTRAINT releasefoundry_billing_portal_public_safe CHECK (
        provider_called = false AND real_charge_possible = false AND raw_payload_included = false AND raw_secrets_included = false AND secret_value_present = false
    )
);

CREATE INDEX IF NOT EXISTS releasefoundry_billing_checkout_scope_idx ON releasefoundry_billing_checkout_plans (tenant_id, project_id, provider, mode, created_at);
CREATE INDEX IF NOT EXISTS releasefoundry_billing_portal_scope_idx ON releasefoundry_billing_portal_plans (tenant_id, project_id, provider, mode, created_at);

CREATE TABLE IF NOT EXISTS releasefoundry_provider_dispatches (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    dispatch_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    operation TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL CHECK (length(request_fingerprint) = 64),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','claimed','indeterminate','reconciling','completed','failed','cancelled')),
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
    PRIMARY KEY (tenant_id, project_id, dispatch_id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES releasefoundry_projects(tenant_id, project_id) ON DELETE CASCADE,
    CONSTRAINT releasefoundry_provider_dispatch_lease_shape CHECK (
        (status IN ('claimed','reconciling') AND lease_owner_id <> '' AND lease_expires_at IS NOT NULL)
        OR (status NOT IN ('claimed','reconciling') AND lease_owner_id = '' AND lease_expires_at IS NULL)
    ),
    CONSTRAINT releasefoundry_provider_dispatch_terminal_proof CHECK (
        (status = 'completed' AND length(terminal_proof_sha256) = 64
          AND length(terminal_response_sha256) = 64 AND completed_at IS NOT NULL
          AND stream_observed = true
          AND stream_observed_fencing_token = fencing_token
          AND stream_observed_sha256 = terminal_proof_sha256)
        OR status <> 'completed'
    ),
    CONSTRAINT releasefoundry_provider_dispatch_stream_observation CHECK (
        (stream_observed = true AND length(stream_observed_sha256) = 64
          AND stream_observed_fencing_token IS NOT NULL AND stream_observed_at IS NOT NULL)
        OR (stream_observed = false AND stream_observed_sha256 = ''
          AND stream_observed_fencing_token IS NULL AND stream_observed_at IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS releasefoundry_provider_dispatch_claim_idx ON releasefoundry_provider_dispatches
    (tenant_id, project_id, status, provider, operation, next_reconcile_at, created_at);
CREATE INDEX IF NOT EXISTS releasefoundry_provider_dispatch_lease_idx ON releasefoundry_provider_dispatches
    (tenant_id, project_id, status, lease_expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS releasefoundry_provider_dispatch_provider_request_idx ON releasefoundry_provider_dispatches
    (tenant_id, project_id, provider, provider_request_id) WHERE provider_request_id <> '';

ALTER TABLE releasefoundry_provider_dispatches ENABLE ROW LEVEL SECURITY;
ALTER TABLE releasefoundry_provider_dispatches FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS releasefoundry_provider_dispatch_tenant_policy ON releasefoundry_provider_dispatches;
DROP POLICY IF EXISTS releasefoundry_provider_dispatch_scope_policy ON releasefoundry_provider_dispatches;
CREATE POLICY releasefoundry_provider_dispatch_scope_policy ON releasefoundry_provider_dispatches
    USING (
        tenant_id = NULLIF(current_setting('app.a1_organization_id', true), '')
        AND project_id = NULLIF(current_setting('app.a1_project_id', true), '')
    )
    WITH CHECK (
        tenant_id = NULLIF(current_setting('app.a1_organization_id', true), '')
        AND project_id = NULLIF(current_setting('app.a1_project_id', true), '')
    );
`

type PostgresRepository struct {
	db    *sql.DB
	now   func() time.Time
	close func() error
}

func OpenPostgresRepository(dsn string) (*PostgresRepository, error) {
	dsn = strings.TrimSpace(dsn)
	if dsn == "" {
		return nil, fmt.Errorf("postgres DSN is required")
	}
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return nil, fmt.Errorf("open postgres repository: %w", err)
	}
	return NewPostgresRepository(db), nil
}

func NewPostgresRepository(db *sql.DB) *PostgresRepository {
	return &PostgresRepository{db: db, now: func() time.Time { return time.Now().UTC() }}
}

func MigratePostgres(ctx context.Context, db *sql.DB) error {
	if db == nil {
		return fmt.Errorf("postgres db is required")
	}
	if _, err := db.ExecContext(ctx, PostgresSchemaSQL); err != nil {
		return fmt.Errorf("migrate postgres schema: %w", err)
	}
	return nil
}

func (repository *PostgresRepository) Migrate(ctx context.Context) error {
	if err := repository.requireDB(); err != nil {
		return err
	}
	return MigratePostgres(ctx, repository.db)
}

func (repository *PostgresRepository) Close() error {
	if repository == nil {
		return nil
	}
	if repository.close != nil {
		return repository.close()
	}
	if repository.db == nil {
		return nil
	}
	return repository.db.Close()
}

func (repository *PostgresRepository) BootstrapProject(tenantName, projectName string, dataset Dataset, tenantID, projectID string) (Envelope[BootstrapResult], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[BootstrapResult]{}, err
	}
	if tenantID == "" {
		tenantID = stablePostgresID("tenant", tenantName)
	}
	if projectID == "" {
		projectID = stablePostgresID("project", projectName)
	}
	if dataset.Name == "" {
		dataset.Name = "SDK Bootstrap Dataset"
	}
	if dataset.DatasetID == "" {
		dataset.DatasetID = stablePostgresID("dataset", dataset.Name)
	}
	tenant := Tenant{TenantID: tenantID, Name: tenantName}
	project := Project{TenantID: tenantID, ProjectID: projectID, Name: projectName}
	dataset.TenantID = tenantID
	dataset.ProjectID = projectID

	ctx := context.Background()
	tx, err := repository.db.BeginTx(ctx, nil)
	if err != nil {
		return Envelope[BootstrapResult]{}, fmt.Errorf("bootstrap project begin transaction: %w", err)
	}
	defer rollbackUnlessCommitted(tx)

	if err := upsertTenant(ctx, tx, tenant); err != nil {
		return Envelope[BootstrapResult]{}, err
	}
	if err := upsertProject(ctx, tx, project); err != nil {
		return Envelope[BootstrapResult]{}, err
	}
	if err := upsertDataset(ctx, tx, dataset); err != nil {
		return Envelope[BootstrapResult]{}, err
	}
	if err := tx.Commit(); err != nil {
		return Envelope[BootstrapResult]{}, fmt.Errorf("bootstrap project commit: %w", err)
	}
	return Envelope[BootstrapResult]{Operation: "bootstrap_project", Status: "ok", Result: BootstrapResult{Tenant: tenant, Project: project, Dataset: dataset}}, nil
}

func (repository *PostgresRepository) SubmitRun(tenantID, projectID, datasetID, agentRef, runID string, metadata JSONMap, options IdempotencyOptions) (Envelope[Run], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[Run]{}, err
	}
	request := JSONMap{"tenant_id": tenantID, "project_id": projectID, "dataset_id": datasetID, "agent_ref": agentRef, "run_id": runID, "metadata": metadata}
	if runID == "" {
		runID = stablePostgresID("run", datasetID)
	}
	mergedMetadata := JSONMap{"client": SaaSClientVersion}
	for key, value := range metadata {
		mergedMetadata[key] = value
	}
	run := Run{TenantID: tenantID, ProjectID: projectID, DatasetID: datasetID, RunID: runID, AgentRef: agentRef, Status: "queued", Metadata: mergedMetadata}
	response := Envelope[Run]{Operation: "sdk_submit", Status: "ok", Result: run}

	ctx := context.Background()
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return Envelope[Run]{}, fmt.Errorf("submit run begin transaction: %w", err)
	}
	defer rollbackUnlessCommitted(tx)

	if options.Key != "" {
		replay, ok, err := loadIdempotentRunReplay(ctx, tx, "sdk_submit", tenantID, projectID, options.Key, request)
		if err != nil || ok {
			return replay, err
		}
	}
	if err := upsertRun(ctx, tx, run); err != nil {
		return Envelope[Run]{}, err
	}
	if err := appendPostgresMutationEvidence(ctx, tx, tenantID, projectID, "sdk.submit", 1, postgresMutationEvidence{APIKeyID: options.APIKeyID, IdempotencyKey: options.Key, RequestID: options.RequestID, RunID: runID, TargetID: runID, After: JSONMap{"run_id": runID, "dataset_id": datasetID, "agent_ref": agentRef}}, repository.now().UTC()); err != nil {
		return Envelope[Run]{}, err
	}
	if options.Key != "" {
		if replay, ok, err := insertIdempotentRunResponse(ctx, tx, "sdk_submit", tenantID, projectID, options.Key, request, response); err != nil || ok {
			return replay, err
		}
	}
	if err := tx.Commit(); err != nil {
		return Envelope[Run]{}, fmt.Errorf("submit run commit: %w", err)
	}
	return response, nil
}

func (repository *PostgresRepository) EnqueueWorkerJob(tenantID, projectID, jobType, targetID string, payload JSONMap, options EnqueueWorkerJobOptions) (Envelope[WorkerJob], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[WorkerJob]{}, err
	}
	normalizedPayload := cloneMap(payload)
	request := JSONMap{"tenant_id": tenantID, "project_id": projectID, "job_type": jobType, "target_id": targetID, "payload": normalizedPayload, "job_id": options.JobID, "priority": options.Priority, "max_attempts": options.MaxAttempts, "api_key_id": options.APIKeyID}
	if strings.TrimSpace(jobType) == "" {
		return Envelope[WorkerJob]{}, fmt.Errorf("job_type is required")
	}
	maxAttempts := options.MaxAttempts
	if maxAttempts == 0 {
		maxAttempts = 3
	}
	if maxAttempts < 1 {
		return Envelope[WorkerJob]{}, fmt.Errorf("max_attempts must be positive")
	}
	priority := options.Priority
	if priority == 0 {
		priority = 100
	}
	payloadSHA, err := fingerprint(normalizedPayload)
	if err != nil {
		return Envelope[WorkerJob]{}, err
	}
	now := repository.now().UTC()
	jobID := options.JobID
	if jobID == "" {
		jobID = stablePostgresWorkerJobID(jobType, now)
	}
	availableAt := now
	job := WorkerJob{SchemaVersion: ControlPlaneSchemaVersion, JobID: jobID, TenantID: tenantID, ProjectID: projectID, JobType: jobType, TargetID: targetID, PayloadSHA256: payloadSHA, RawPayloadIncluded: false, Status: WorkerJobStatusQueued, Priority: priority, Attempts: 0, MaxAttempts: maxAttempts, AvailableAt: &availableAt, IdempotencyKey: options.IdempotencyKey, RequestID: options.RequestID, CreatedAt: now, UpdatedAt: now}
	response := Envelope[WorkerJob]{Operation: "worker.job.enqueue", Status: "ok", Result: job}

	ctx := context.Background()
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return Envelope[WorkerJob]{}, fmt.Errorf("enqueue worker job begin transaction: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	if err := requireProject(ctx, tx, tenantID, projectID); err != nil {
		return Envelope[WorkerJob]{}, err
	}
	if options.IdempotencyKey != "" {
		replay, ok, err := loadIdempotentWorkerJobReplay(ctx, tx, "worker.job.enqueue", tenantID, projectID, options.IdempotencyKey, request)
		if err != nil || ok {
			return replay, err
		}
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO releasefoundry_worker_jobs (tenant_id, project_id, job_id, job_type, target_id, payload_sha256, status, priority, attempts, max_attempts, available_at, idempotency_key, request_id, created_at, updated_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 0, $9, $10, $11, $12, $13, $13)
`, job.TenantID, job.ProjectID, job.JobID, job.JobType, job.TargetID, job.PayloadSHA256, job.Status, job.Priority, job.MaxAttempts, job.AvailableAt, job.IdempotencyKey, job.RequestID, now)
	if err != nil {
		return Envelope[WorkerJob]{}, fmt.Errorf("insert worker job: %w", err)
	}
	if err := appendPostgresMutationEvidence(ctx, tx, tenantID, projectID, "worker.job.enqueue", 1, postgresMutationEvidence{APIKeyID: options.APIKeyID, IdempotencyKey: options.IdempotencyKey, RequestID: options.RequestID, RunID: targetID, TargetID: jobID, After: JSONMap{"job_id": jobID, "job_type": jobType, "target_id": targetID, "payload_sha256": payloadSHA}}, now); err != nil {
		return Envelope[WorkerJob]{}, err
	}
	if options.IdempotencyKey != "" {
		if replay, ok, err := insertIdempotentWorkerJobResponse(ctx, tx, "worker.job.enqueue", tenantID, projectID, options.IdempotencyKey, request, response); err != nil || ok {
			return replay, err
		}
	}
	if err := tx.Commit(); err != nil {
		return Envelope[WorkerJob]{}, fmt.Errorf("enqueue worker job commit: %w", err)
	}
	return response, nil
}

func (repository *PostgresRepository) LeaseWorkerJob(tenantID, projectID, leaseOwnerID string, options LeaseWorkerJobOptions) (Envelope[WorkerLeaseResult], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[WorkerLeaseResult]{}, err
	}
	if strings.TrimSpace(leaseOwnerID) == "" {
		return Envelope[WorkerLeaseResult]{}, fmt.Errorf("lease_owner_id is required")
	}
	leaseSeconds := options.LeaseSeconds
	if leaseSeconds == 0 {
		leaseSeconds = 300
	}
	if leaseSeconds < 1 {
		return Envelope[WorkerLeaseResult]{}, fmt.Errorf("lease_seconds must be positive")
	}
	now := repository.now().UTC()
	leaseExpiresAt := now.Add(time.Duration(leaseSeconds) * time.Second)

	ctx := context.Background()
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return Envelope[WorkerLeaseResult]{}, fmt.Errorf("lease worker job begin transaction: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	if err := requireProject(ctx, tx, tenantID, projectID); err != nil {
		return Envelope[WorkerLeaseResult]{}, err
	}
	if err := expirePostgresWorkerLeases(ctx, tx, tenantID, projectID, now); err != nil {
		return Envelope[WorkerLeaseResult]{}, err
	}
	job, err := selectPostgresWorkerJobForLease(ctx, tx, tenantID, projectID, options.JobType, now)
	if errors.Is(err, sql.ErrNoRows) {
		result := WorkerLeaseResult{SchemaVersion: ControlPlaneSchemaVersion, Status: "empty", TenantID: tenantID, ProjectID: projectID, Leased: false, Job: nil, CreatedAt: now}
		if err := tx.Commit(); err != nil {
			return Envelope[WorkerLeaseResult]{}, fmt.Errorf("lease worker job empty commit: %w", err)
		}
		return Envelope[WorkerLeaseResult]{Operation: "worker.job.lease", Status: "ok", Result: result}, nil
	}
	if err != nil {
		return Envelope[WorkerLeaseResult]{}, err
	}
	job, err = updatePostgresWorkerJobLease(ctx, tx, tenantID, projectID, job.JobID, leaseOwnerID, leaseExpiresAt, now)
	if err != nil {
		return Envelope[WorkerLeaseResult]{}, err
	}
	if err := appendPostgresMutationEvidence(ctx, tx, tenantID, projectID, "worker.job.lease", 0, postgresMutationEvidence{IdempotencyKey: job.IdempotencyKey, RequestID: job.RequestID, RunID: job.TargetID, TargetID: job.JobID, After: JSONMap{"job_id": job.JobID, "job_type": job.JobType, "lease_owner_id": leaseOwnerID, "lease_expires_at": leaseExpiresAt}}, now); err != nil {
		return Envelope[WorkerLeaseResult]{}, err
	}
	if err := tx.Commit(); err != nil {
		return Envelope[WorkerLeaseResult]{}, fmt.Errorf("lease worker job commit: %w", err)
	}
	resultJob := job
	result := WorkerLeaseResult{SchemaVersion: ControlPlaneSchemaVersion, Status: "leased", TenantID: tenantID, ProjectID: projectID, Leased: true, Job: &resultJob}
	return Envelope[WorkerLeaseResult]{Operation: "worker.job.lease", Status: "ok", Result: result}, nil
}

func (repository *PostgresRepository) HeartbeatWorkerJob(tenantID, projectID, jobID, leaseOwnerID string, leaseSeconds int) (Envelope[WorkerJob], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[WorkerJob]{}, err
	}
	if leaseSeconds == 0 {
		leaseSeconds = 300
	}
	if leaseSeconds < 1 {
		return Envelope[WorkerJob]{}, fmt.Errorf("lease_seconds must be positive")
	}
	now := repository.now().UTC()
	leaseExpiresAt := now.Add(time.Duration(leaseSeconds) * time.Second)
	return repository.mutateLeasedWorkerJob(tenantID, projectID, jobID, leaseOwnerID, now, "worker.job.heartbeat", func(ctx context.Context, tx *sql.Tx, job WorkerJob) (WorkerJob, error) {
		return updatePostgresWorkerJobHeartbeat(ctx, tx, tenantID, projectID, job.JobID, leaseExpiresAt, now)
	})
}

func (repository *PostgresRepository) CompleteWorkerJob(tenantID, projectID, jobID, leaseOwnerID string, result JSONMap, options CompleteWorkerJobOptions) (Envelope[WorkerJob], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[WorkerJob]{}, err
	}
	resultSHA, err := fingerprint(cloneMap(result))
	if err != nil {
		return Envelope[WorkerJob]{}, err
	}
	now := repository.now().UTC()
	return repository.mutateLeasedWorkerJob(tenantID, projectID, jobID, leaseOwnerID, now, "worker.job.complete", func(ctx context.Context, tx *sql.Tx, job WorkerJob) (WorkerJob, error) {
		return updatePostgresWorkerJobComplete(ctx, tx, tenantID, projectID, job.JobID, resultSHA, now)
	})
}

func (repository *PostgresRepository) FailWorkerJob(tenantID, projectID, jobID, leaseOwnerID string, failure JSONMap, options FailWorkerJobOptions) (Envelope[WorkerJob], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[WorkerJob]{}, err
	}
	failure = cloneMap(failure)
	failureSHA, err := fingerprint(failure)
	if err != nil {
		return Envelope[WorkerJob]{}, err
	}
	now := repository.now().UTC()
	errorType, _ := failure["type"].(string)
	if strings.TrimSpace(errorType) == "" {
		errorType = "worker_error"
	}
	message, _ := failure["message"].(string)
	if strings.TrimSpace(message) == "" {
		message = "redacted"
	}
	lastError := WorkerJobError{SHA256: failureSHA, Type: errorType, Message: message, RawPayloadIncluded: false, FailedAt: now}
	return repository.mutateLeasedWorkerJob(tenantID, projectID, jobID, leaseOwnerID, now, "worker.job.fail", func(ctx context.Context, tx *sql.Tx, job WorkerJob) (WorkerJob, error) {
		availableAt := (*time.Time)(nil)
		deadLetteredAt := (*time.Time)(nil)
		status := WorkerJobStatusDeadLettered
		if job.Attempts < job.MaxAttempts {
			status = WorkerJobStatusRetrying
			retrySeconds := retryAfterSeconds(job.Attempts, options.RetryAfterSeconds)
			next := now.Add(time.Duration(retrySeconds) * time.Second)
			availableAt = &next
		} else {
			deadLetteredAt = &now
		}
		return updatePostgresWorkerJobFail(ctx, tx, tenantID, projectID, job.JobID, status, availableAt, deadLetteredAt, lastError, now)
	})
}

func (repository *PostgresRepository) ListWorkerJobs(tenantID, projectID string, options ListWorkerJobsOptions) (Envelope[WorkerJobList], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[WorkerJobList]{}, err
	}
	ctx := context.Background()
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable, ReadOnly: false})
	if err != nil {
		return Envelope[WorkerJobList]{}, fmt.Errorf("list worker jobs begin transaction: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	if err := requireProject(ctx, tx, tenantID, projectID); err != nil {
		return Envelope[WorkerJobList]{}, err
	}
	if err := expirePostgresWorkerLeases(ctx, tx, tenantID, projectID, repository.now().UTC()); err != nil {
		return Envelope[WorkerJobList]{}, err
	}
	var limit any
	if options.Limit > 0 {
		limit = options.Limit
	}
	rows, err := tx.QueryContext(ctx, `
SELECT job_id, tenant_id, project_id, job_type, target_id, payload_sha256, status, priority, attempts, max_attempts, lease_owner_id, lease_expires_at, available_at, last_error, result_sha256, idempotency_key, request_id, created_at, updated_at, completed_at, dead_lettered_at
FROM releasefoundry_worker_jobs
WHERE tenant_id = $1 AND project_id = $2 AND ($3 = '' OR status = $3) AND ($4 = '' OR job_type = $4)
ORDER BY priority ASC, available_at ASC NULLS FIRST, created_at ASC, job_id ASC
LIMIT $5
`, tenantID, projectID, options.Status, options.JobType, limit)
	if err != nil {
		return Envelope[WorkerJobList]{}, fmt.Errorf("list worker jobs: %w", err)
	}
	defer rows.Close()
	jobs := []WorkerJob{}
	for rows.Next() {
		job, err := scanPostgresWorkerJob(rows)
		if err != nil {
			return Envelope[WorkerJobList]{}, err
		}
		jobs = append(jobs, job)
	}
	if err := rows.Err(); err != nil {
		return Envelope[WorkerJobList]{}, fmt.Errorf("iterate worker jobs: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return Envelope[WorkerJobList]{}, fmt.Errorf("list worker jobs commit: %w", err)
	}
	filters := JSONMap{"status": options.Status, "job_type": options.JobType, "limit": options.Limit}
	result := WorkerJobList{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, Filters: filters, Jobs: jobs, Count: len(jobs)}
	return Envelope[WorkerJobList]{Operation: "worker.job.list", Status: "ok", Result: result}, nil
}

func (repository *PostgresRepository) UploadRun(tenantID, projectID, runID string, result JSONMap, options UploadRunOptions) (Envelope[RunUpload], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[RunUpload]{}, err
	}
	if err := ValidateMediaSafeEnvelope(result); err != nil {
		return Envelope[RunUpload]{}, err
	}
	request := JSONMap{"tenant_id": tenantID, "project_id": projectID, "run_id": runID, "result": result, "upload_id": options.UploadID}
	now := repository.now().UTC()
	uploadID := options.UploadID
	if uploadID == "" {
		uploadID = stablePostgresTimedID("upload", runID, now)
	}
	resultSHA, err := fingerprint(result)
	if err != nil {
		return Envelope[RunUpload]{}, err
	}
	upload := RunUpload{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, RunID: runID, UploadID: uploadID, ResultSHA256: resultSHA, RawPayloadIncluded: false, APIKeyID: options.APIKeyID, RequestID: options.RequestID, CreatedAt: now}
	response := Envelope[RunUpload]{Operation: "upload_run", Status: "ok", Result: upload}

	ctx := context.Background()
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return Envelope[RunUpload]{}, fmt.Errorf("upload run begin transaction: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	if err := requireRun(ctx, tx, tenantID, projectID, runID); err != nil {
		return Envelope[RunUpload]{}, err
	}
	if options.IdempotencyKey != "" {
		replay, ok, err := loadIdempotentRunUploadReplay(ctx, tx, "upload_run", tenantID, projectID, options.IdempotencyKey, request)
		if err != nil || ok {
			return replay, err
		}
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO releasefoundry_run_uploads (tenant_id, project_id, run_id, upload_id, result_sha256, api_key_id, request_id, idempotency_key, created_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
`, tenantID, projectID, runID, uploadID, resultSHA, options.APIKeyID, options.RequestID, options.IdempotencyKey, now)
	if err != nil {
		return Envelope[RunUpload]{}, fmt.Errorf("insert run upload: %w", err)
	}
	_, err = tx.ExecContext(ctx, `
UPDATE releasefoundry_runs SET status = 'uploaded', updated_at = $4
WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3
`, tenantID, projectID, runID, now)
	if err != nil {
		return Envelope[RunUpload]{}, fmt.Errorf("mark run uploaded: %w", err)
	}
	if err := appendPostgresMutationEvidence(ctx, tx, tenantID, projectID, "run.upload", 1, postgresMutationEvidence{APIKeyID: options.APIKeyID, IdempotencyKey: options.IdempotencyKey, RequestID: options.RequestID, RunID: runID, TargetID: runID, After: JSONMap{"run_id": runID, "upload_id": uploadID, "result_sha256": resultSHA}}, now); err != nil {
		return Envelope[RunUpload]{}, err
	}
	if options.IdempotencyKey != "" {
		if replay, ok, err := insertIdempotentRunUploadResponse(ctx, tx, "upload_run", tenantID, projectID, options.IdempotencyKey, request, response); err != nil || ok {
			return replay, err
		}
	}
	if err := tx.Commit(); err != nil {
		return Envelope[RunUpload]{}, fmt.Errorf("upload run commit: %w", err)
	}
	return response, nil
}

func (repository *PostgresRepository) IngestTrace(tenantID, projectID, runID string, observations []JSONMap, options IngestTraceOptions) (Envelope[TraceBatch], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[TraceBatch]{}, err
	}
	if err := ValidateMediaSafeEnvelope(observations); err != nil {
		return Envelope[TraceBatch]{}, err
	}
	if len(observations) == 0 {
		return Envelope[TraceBatch]{}, fmt.Errorf("trace ingestion requires at least one observation")
	}
	request := JSONMap{"tenant_id": tenantID, "project_id": projectID, "run_id": runID, "observations": observations, "batch_id": options.BatchID}
	now := repository.now().UTC()
	batchID := options.BatchID
	if batchID == "" {
		batchID = stablePostgresTimedID("trace_batch", runID, now)
	}
	observationsSHA, err := fingerprint(observations)
	if err != nil {
		return Envelope[TraceBatch]{}, err
	}
	batch := TraceBatch{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, RunID: runID, BatchID: batchID, ObservationCount: len(observations), ObservationsSHA256: observationsSHA, RawPayloadIncluded: false, APIKeyID: options.APIKeyID, RequestID: options.RequestID, CreatedAt: now}
	response := Envelope[TraceBatch]{Operation: "ingest_trace", Status: "ok", Result: batch}

	ctx := context.Background()
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return Envelope[TraceBatch]{}, fmt.Errorf("ingest trace begin transaction: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	if err := requireRun(ctx, tx, tenantID, projectID, runID); err != nil {
		return Envelope[TraceBatch]{}, err
	}
	if options.IdempotencyKey != "" {
		replay, ok, err := loadIdempotentTraceBatchReplay(ctx, tx, "ingest_trace", tenantID, projectID, options.IdempotencyKey, request)
		if err != nil || ok {
			return replay, err
		}
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO releasefoundry_trace_batches (tenant_id, project_id, run_id, batch_id, observation_count, observations_sha256, api_key_id, request_id, idempotency_key, created_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
`, tenantID, projectID, runID, batchID, len(observations), observationsSHA, options.APIKeyID, options.RequestID, options.IdempotencyKey, now)
	if err != nil {
		return Envelope[TraceBatch]{}, fmt.Errorf("insert trace batch: %w", err)
	}
	if err := appendPostgresMutationEvidence(ctx, tx, tenantID, projectID, "trace.ingest", len(observations), postgresMutationEvidence{APIKeyID: options.APIKeyID, IdempotencyKey: options.IdempotencyKey, RequestID: options.RequestID, RunID: runID, TargetID: runID, After: JSONMap{"run_id": runID, "batch_id": batchID, "observation_count": len(observations), "observations_sha256": observationsSHA}}, now); err != nil {
		return Envelope[TraceBatch]{}, err
	}
	if options.IdempotencyKey != "" {
		if replay, ok, err := insertIdempotentTraceBatchResponse(ctx, tx, "ingest_trace", tenantID, projectID, options.IdempotencyKey, request, response); err != nil || ok {
			return replay, err
		}
	}
	if err := tx.Commit(); err != nil {
		return Envelope[TraceBatch]{}, fmt.Errorf("ingest trace commit: %w", err)
	}
	return response, nil
}

func (repository *PostgresRepository) CreateArtifactManifest(tenantID, projectID, runID string, manifest JSONMap, options ArtifactManifestOptions) (Envelope[ArtifactManifest], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[ArtifactManifest]{}, err
	}
	if err := ValidateMediaSafeEnvelope(manifest); err != nil {
		return Envelope[ArtifactManifest]{}, err
	}
	request := JSONMap{"tenant_id": tenantID, "project_id": projectID, "run_id": runID, "manifest": manifest, "artifact_id": options.ArtifactID}
	now := repository.now().UTC()
	artifactID := options.ArtifactID
	if artifactID == "" {
		artifactID = stablePostgresTimedID("artifact", runID, now)
	}
	manifestSHA, err := fingerprint(manifest)
	if err != nil {
		return Envelope[ArtifactManifest]{}, err
	}
	record := ArtifactManifest{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, RunID: runID, ArtifactID: artifactID, ManifestSHA256: manifestSHA, RawPayloadIncluded: false, APIKeyID: options.APIKeyID, RequestID: options.RequestID, CreatedAt: now}
	response := Envelope[ArtifactManifest]{Operation: "artifact_manifest", Status: "ok", Result: record}

	ctx := context.Background()
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return Envelope[ArtifactManifest]{}, fmt.Errorf("create artifact manifest begin transaction: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	if err := requireRun(ctx, tx, tenantID, projectID, runID); err != nil {
		return Envelope[ArtifactManifest]{}, err
	}
	if options.IdempotencyKey != "" {
		replay, ok, err := loadIdempotentArtifactManifestReplay(ctx, tx, "artifact_manifest", tenantID, projectID, options.IdempotencyKey, request)
		if err != nil || ok {
			return replay, err
		}
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO releasefoundry_artifact_manifests (tenant_id, project_id, run_id, artifact_id, manifest_sha256, api_key_id, request_id, idempotency_key, created_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
`, tenantID, projectID, runID, artifactID, manifestSHA, options.APIKeyID, options.RequestID, options.IdempotencyKey, now)
	if err != nil {
		return Envelope[ArtifactManifest]{}, fmt.Errorf("insert artifact manifest: %w", err)
	}
	if err := appendPostgresMutationEvidence(ctx, tx, tenantID, projectID, "artifact.manifest", 1, postgresMutationEvidence{APIKeyID: options.APIKeyID, IdempotencyKey: options.IdempotencyKey, RequestID: options.RequestID, RunID: runID, TargetID: runID, After: JSONMap{"run_id": runID, "artifact_id": artifactID, "manifest_sha256": manifestSHA}}, now); err != nil {
		return Envelope[ArtifactManifest]{}, err
	}
	if options.IdempotencyKey != "" {
		if replay, ok, err := insertIdempotentArtifactManifestResponse(ctx, tx, "artifact_manifest", tenantID, projectID, options.IdempotencyKey, request, response); err != nil || ok {
			return replay, err
		}
	}
	if err := tx.Commit(); err != nil {
		return Envelope[ArtifactManifest]{}, fmt.Errorf("create artifact manifest commit: %w", err)
	}
	return response, nil
}

func (repository *PostgresRepository) ListArtifactManifests(tenantID, projectID, runID string) (Envelope[ArtifactManifestList], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[ArtifactManifestList]{}, err
	}
	ctx := context.Background()
	manifests, err := repository.postgresArtifactManifests(ctx, tenantID, projectID, runID)
	if err != nil {
		return Envelope[ArtifactManifestList]{}, err
	}
	result := ArtifactManifestList{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, RunID: runID, Manifests: manifests, Count: len(manifests)}
	return Envelope[ArtifactManifestList]{Operation: "artifact_manifests", Status: "ok", Result: result}, nil
}

func (repository *PostgresRepository) RunLifecycle(tenantID, projectID, runID string) (Envelope[RunLifecycle], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[RunLifecycle]{}, err
	}
	ctx := context.Background()
	run, err := repository.postgresRun(ctx, tenantID, projectID, runID)
	if err != nil {
		return Envelope[RunLifecycle]{}, err
	}
	uploads, err := repository.postgresRunUploads(ctx, tenantID, projectID, runID)
	if err != nil {
		return Envelope[RunLifecycle]{}, err
	}
	traceBatches, err := repository.postgresTraceBatches(ctx, tenantID, projectID, runID)
	if err != nil {
		return Envelope[RunLifecycle]{}, err
	}
	artifacts, err := repository.postgresArtifactManifests(ctx, tenantID, projectID, runID)
	if err != nil {
		return Envelope[RunLifecycle]{}, err
	}
	result := RunLifecycle{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, RunID: runID, Run: run, Uploads: uploads, TraceBatches: traceBatches, Artifacts: artifacts, Counts: JSONMap{"uploads": len(uploads), "trace_batches": len(traceBatches), "artifacts": len(artifacts)}, GeneratedAt: repository.now()}
	return Envelope[RunLifecycle]{Operation: "lifecycle", Status: "ok", Result: result}, nil
}

func (repository *PostgresRepository) VerifyAuditChain(tenantID, projectID string) (Envelope[AuditChainVerification], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[AuditChainVerification]{}, err
	}
	ctx := context.Background()
	rows, err := repository.db.QueryContext(ctx, `
SELECT tenant_id, project_id, audit_event_id, action, target_id, api_key_id, idempotency_key, request_id, previous_hash, event_hash, after_json, created_at
FROM releasefoundry_audit_events
WHERE tenant_id = $1 AND project_id = $2
ORDER BY created_at ASC, audit_event_id ASC
`, tenantID, projectID)
	if err != nil {
		return Envelope[AuditChainVerification]{}, fmt.Errorf("verify audit chain query: %w", err)
	}
	defer rows.Close()

	result, err := verifyPostgresAuditChainRows(rows, tenantID, projectID, repository.now().UTC())
	if err != nil {
		return Envelope[AuditChainVerification]{}, err
	}
	return Envelope[AuditChainVerification]{Operation: "audit.chain.verify", Status: "ok", Result: result}, nil
}

func (repository *PostgresRepository) AuditLog(tenantID, projectID string, options AuditLogOptions) (Envelope[AuditEventList], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[AuditEventList]{}, err
	}
	ctx := context.Background()
	rows, err := repository.db.QueryContext(ctx, `
SELECT tenant_id, project_id, audit_event_id, action, target_id, api_key_id, idempotency_key, request_id, previous_hash, event_hash, after_json, created_at
FROM releasefoundry_audit_events
WHERE tenant_id = $1 AND project_id = $2
ORDER BY created_at ASC, audit_event_id ASC
`, tenantID, projectID)
	if err != nil {
		return Envelope[AuditEventList]{}, fmt.Errorf("audit log query: %w", err)
	}
	defer rows.Close()
	events := []AuditEvent{}
	for rows.Next() {
		event, err := scanPostgresAuditEvent(rows)
		if err != nil {
			return Envelope[AuditEventList]{}, err
		}
		events = append(events, event)
	}
	if err := rows.Err(); err != nil {
		return Envelope[AuditEventList]{}, fmt.Errorf("iterate audit log: %w", err)
	}
	filtered := filterAuditEvents(events, options.RunID, options.ActionPrefix, options.Limit)
	result := AuditEventList{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, RunID: options.RunID, ActionPrefix: options.ActionPrefix, Events: filtered, Count: len(filtered)}
	return Envelope[AuditEventList]{Operation: "audit_log", Status: "ok", Result: result}, nil
}

func (repository *PostgresRepository) BuildReleaseEvidencePacket(tenantID, projectID, runID string) (Envelope[ReleaseEvidencePacket], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[ReleaseEvidencePacket]{}, err
	}
	ctx := context.Background()
	run, err := repository.postgresRun(ctx, tenantID, projectID, runID)
	if err != nil {
		return Envelope[ReleaseEvidencePacket]{}, err
	}
	now := repository.now().UTC()
	verification, err := repository.VerifyAuditChain(tenantID, projectID)
	if err != nil {
		return Envelope[ReleaseEvidencePacket]{}, err
	}
	uploads, err := repository.postgresRunUploads(ctx, tenantID, projectID, runID)
	if err != nil {
		return Envelope[ReleaseEvidencePacket]{}, err
	}
	batches, err := repository.postgresTraceBatches(ctx, tenantID, projectID, runID)
	if err != nil {
		return Envelope[ReleaseEvidencePacket]{}, err
	}
	manifests, err := repository.ListArtifactManifests(tenantID, projectID, runID)
	if err != nil {
		return Envelope[ReleaseEvidencePacket]{}, err
	}
	packet := ReleaseEvidencePacket{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, RunID: runID, PacketID: "release_evidence_" + mustFingerprint(JSONMap{"tenant_id": tenantID, "project_id": projectID, "run_id": runID})[:16], Run: run, Uploads: uploads, TraceBatches: batches, ArtifactManifests: manifests.Result.Manifests, AuditVerification: verification.Result, GeneratedAt: now}
	packet.PacketSHA256 = releaseEvidencePacketSHA(packet)
	return Envelope[ReleaseEvidencePacket]{Operation: "release_evidence", Status: "ok", Result: packet}, nil
}

func (repository *PostgresRepository) VerifyReleaseEvidencePacket(tenantID, projectID, runID string, packet JSONMap) (Envelope[ReleaseEvidenceVerification], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[ReleaseEvidenceVerification]{}, err
	}
	result := verifyReleaseEvidencePacketMap(tenantID, projectID, runID, packet, repository.now().UTC())
	return Envelope[ReleaseEvidenceVerification]{Operation: "release_evidence.verify", Status: "ok", Result: result}, nil
}

func (repository *PostgresRepository) UsageSnapshot(tenantID, projectID string) (Envelope[UsageSnapshot], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[UsageSnapshot]{}, err
	}
	ctx := context.Background()
	rows, err := repository.db.QueryContext(ctx, `
SELECT operation, COALESCE(SUM(units), 0)::int, COUNT(*)::int
FROM releasefoundry_quota_ledger
WHERE tenant_id = $1 AND project_id = $2
GROUP BY operation
ORDER BY operation ASC
`, tenantID, projectID)
	if err != nil {
		return Envelope[UsageSnapshot]{}, fmt.Errorf("usage snapshot query: %w", err)
	}
	defer rows.Close()
	result := UsageSnapshot{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, GeneratedAt: repository.now().UTC()}
	for rows.Next() {
		var total UsageOperationTotal
		if err := rows.Scan(&total.Operation, &total.Units, &total.Events); err != nil {
			return Envelope[UsageSnapshot]{}, fmt.Errorf("scan usage snapshot: %w", err)
		}
		result.OperationTotals = append(result.OperationTotals, total)
		result.TotalUnits += total.Units
		result.TotalEvents += total.Events
	}
	if err := rows.Err(); err != nil {
		return Envelope[UsageSnapshot]{}, fmt.Errorf("iterate usage snapshot: %w", err)
	}
	return Envelope[UsageSnapshot]{Operation: "usage", Status: "ok", Result: result}, nil
}

func (repository *PostgresRepository) CreateBillingCheckoutPlan(tenantID, projectID string, request BillingPlanRequest, options IdempotencyOptions) (Envelope[BillingCheckoutPlan], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[BillingCheckoutPlan]{}, err
	}
	planID := normalizeBillingPlanID(request.PlanID)
	if planID == "" {
		return Envelope[BillingCheckoutPlan]{}, fmt.Errorf("billing plan_id is required")
	}
	cycle := normalizeBillingCycle(request.BillingCycle)
	providerConfig := publicBillingProviderConfig(request.ProviderConfig)
	if len(providerConfig) == 0 || strings.TrimSpace(stringFromAny(providerConfig["provider"])) == "" {
		return Envelope[BillingCheckoutPlan]{}, fmt.Errorf("billing provider_config.provider is required")
	}
	provider := billingProviderFromConfig(providerConfig)
	mode := billingModeFromConfig(providerConfig, "deterministic_contract")
	price := sanitizedBillingMetadata(request.Price)
	metadata := sanitizedBillingMetadata(request.Metadata)
	customerRef := strings.TrimSpace(request.CustomerRef)
	successURL := strings.TrimSpace(request.SuccessURL)
	cancelURL := strings.TrimSpace(request.CancelURL)
	requestFingerprint := JSONMap{"tenant_id": tenantID, "project_id": projectID, "plan_id": planID, "billing_cycle": cycle, "provider": provider, "mode": mode, "customer_ref": customerRef, "price": price, "success_url": successURL, "cancel_url": cancelURL, "idempotency_key": options.Key}
	fingerprint := mustFingerprint(requestFingerprint)
	now := repository.now().UTC().Truncate(time.Microsecond)
	result := BillingCheckoutPlan{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, PlanID: planID, BillingCycle: cycle, CheckoutID: "checkout_" + fingerprint[:16], CheckoutURL: "https://billing.local.releasefoundry.invalid/checkout/" + fingerprint[:24], Mode: mode, Provider: provider, ProviderConfig: providerConfig, CustomerRef: customerRef, Price: price, SuccessURL: successURL, CancelURL: cancelURL, SideEffects: billingSafeSideEffects(), ProviderCalled: false, RealChargePossible: false, PublicSafe: true, RawPayloadIncluded: false, RawSecretsIncluded: false, SecretValuePresent: false, Metadata: metadata, CreatedAt: now}
	response := Envelope[BillingCheckoutPlan]{Operation: "billing.checkout_plan", Status: "ok", Result: result}

	ctx := context.Background()
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return Envelope[BillingCheckoutPlan]{}, fmt.Errorf("billing checkout begin transaction: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	if options.Key != "" {
		if replay, ok, err := loadIdempotentBillingCheckoutPlanReplay(ctx, tx, response.Operation, tenantID, projectID, options.Key, requestFingerprint); err != nil || ok {
			return replay, err
		}
	}
	if err := requireProject(ctx, tx, tenantID, projectID); err != nil {
		return Envelope[BillingCheckoutPlan]{}, err
	}
	if err := insertPostgresBillingCheckoutPlan(ctx, tx, result, options); err != nil {
		return Envelope[BillingCheckoutPlan]{}, err
	}
	if err := appendPostgresMutationEvidence(ctx, tx, tenantID, projectID, response.Operation, 1, postgresMutationEvidence{APIKeyID: options.APIKeyID, IdempotencyKey: options.Key, RequestID: options.RequestID, TargetID: result.CheckoutID, After: JSONMap{"checkout_id": result.CheckoutID, "plan_id": planID, "billing_cycle": cycle, "provider": provider, "raw_payload_included": false}}, now); err != nil {
		return Envelope[BillingCheckoutPlan]{}, err
	}
	if options.Key != "" {
		if replay, ok, err := insertIdempotentBillingCheckoutPlanResponse(ctx, tx, response.Operation, tenantID, projectID, options.Key, requestFingerprint, response); err != nil || ok {
			return replay, err
		}
	}
	if err := tx.Commit(); err != nil {
		return Envelope[BillingCheckoutPlan]{}, fmt.Errorf("billing checkout commit: %w", err)
	}
	return response, nil
}

func (repository *PostgresRepository) CreateBillingPortalPlan(tenantID, projectID string, request BillingPlanRequest, options IdempotencyOptions) (Envelope[BillingPortalPlan], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[BillingPortalPlan]{}, err
	}
	planID := normalizeBillingPlanID(request.PlanID)
	providerConfig := publicBillingProviderConfig(request.ProviderConfig)
	if len(providerConfig) == 0 || strings.TrimSpace(stringFromAny(providerConfig["provider"])) == "" {
		return Envelope[BillingPortalPlan]{}, fmt.Errorf("billing provider_config.provider is required")
	}
	provider := billingProviderFromConfig(providerConfig)
	if provider != "stripe" {
		return Envelope[BillingPortalPlan]{}, fmt.Errorf("billing portal requires explicit stripe provider")
	}
	mode := billingModeFromConfig(providerConfig, "deterministic_contract")
	customerRef := strings.TrimSpace(request.CustomerRef)
	returnURL := strings.TrimSpace(request.ReturnURL)
	requestFingerprint := JSONMap{"tenant_id": tenantID, "project_id": projectID, "plan_id": planID, "provider": provider, "mode": mode, "customer_ref": customerRef, "return_url": returnURL, "idempotency_key": options.Key}
	fingerprint := mustFingerprint(requestFingerprint)
	now := repository.now().UTC().Truncate(time.Microsecond)
	result := BillingPortalPlan{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, PlanID: planID, PortalSessionID: "portal_" + fingerprint[:16], PortalURL: "https://billing.local.releasefoundry.invalid/portal/" + fingerprint[:24], Mode: mode, Provider: provider, ProviderConfig: providerConfig, CustomerRef: customerRef, ReturnURL: returnURL, SideEffects: billingSafeSideEffects(), ProviderCalled: false, RealChargePossible: false, PublicSafe: true, RawPayloadIncluded: false, RawSecretsIncluded: false, SecretValuePresent: false, CreatedAt: now}
	response := Envelope[BillingPortalPlan]{Operation: "billing.portal_plan", Status: "ok", Result: result}

	ctx := context.Background()
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return Envelope[BillingPortalPlan]{}, fmt.Errorf("billing portal begin transaction: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	if options.Key != "" {
		if replay, ok, err := loadIdempotentBillingPortalPlanReplay(ctx, tx, response.Operation, tenantID, projectID, options.Key, requestFingerprint); err != nil || ok {
			return replay, err
		}
	}
	if err := requireProject(ctx, tx, tenantID, projectID); err != nil {
		return Envelope[BillingPortalPlan]{}, err
	}
	if err := insertPostgresBillingPortalPlan(ctx, tx, result, options); err != nil {
		return Envelope[BillingPortalPlan]{}, err
	}
	if err := appendPostgresMutationEvidence(ctx, tx, tenantID, projectID, response.Operation, 1, postgresMutationEvidence{APIKeyID: options.APIKeyID, IdempotencyKey: options.Key, RequestID: options.RequestID, TargetID: result.PortalSessionID, After: JSONMap{"portal_session_id": result.PortalSessionID, "plan_id": planID, "provider": provider, "raw_payload_included": false}}, now); err != nil {
		return Envelope[BillingPortalPlan]{}, err
	}
	if options.Key != "" {
		if replay, ok, err := insertIdempotentBillingPortalPlanResponse(ctx, tx, response.Operation, tenantID, projectID, options.Key, requestFingerprint, response); err != nil || ok {
			return replay, err
		}
	}
	if err := tx.Commit(); err != nil {
		return Envelope[BillingPortalPlan]{}, fmt.Errorf("billing portal commit: %w", err)
	}
	return response, nil
}

func (repository *PostgresRepository) IngestBillingWebhook(tenantID, projectID string, event BillingWebhookIngest, options IdempotencyOptions) (Envelope[BillingWebhookIngest], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[BillingWebhookIngest]{}, err
	}
	event.TenantID = tenantID
	event.ProjectID = projectID
	event.SchemaVersion = ControlPlaneSchemaVersion
	event.EventType = strings.TrimSpace(event.EventType)
	if event.EventType == "" {
		return Envelope[BillingWebhookIngest]{}, fmt.Errorf("billing webhook event_type is required")
	}
	event.Provider = normalizeBillingProvider(event.Provider)
	event.Mode = normalizeBillingMode(event.Mode)
	event.PlanID = normalizeBillingPlanID(event.PlanID)
	event.CustomerRef = strings.TrimSpace(event.CustomerRef)
	event.Status = normalizeBillingStatus(event.Status)
	event.Metadata = sanitizedBillingMetadata(event.Metadata)
	event.RawPayloadIncluded = false
	event.SecretValuePresent = false
	event.WebhookSecretRef = strings.TrimSpace(event.WebhookSecretRef)
	payloadFingerprint := strings.ToLower(strings.TrimSpace(event.PayloadSHA256))
	if payloadFingerprint == "" {
		payloadFingerprint = mustFingerprint(JSONMap{"tenant_id": tenantID, "project_id": projectID, "event_type": event.EventType, "provider": event.Provider, "mode": event.Mode, "plan_id": event.PlanID, "customer_ref": event.CustomerRef, "status": event.Status, "metadata": event.Metadata})
	}
	if !looksLikeSHA256Hex(payloadFingerprint) {
		return Envelope[BillingWebhookIngest]{}, fmt.Errorf("billing webhook payload_sha256 must be a sha256 hex digest")
	}
	event.PayloadSHA256 = payloadFingerprint
	event.Failures = billingWebhookFailures(event)
	event.Verified = false
	event.Failures = appendBillingWebhookFailure(event.Failures, "provider_specific_verification_required")
	if strings.TrimSpace(event.EventID) == "" {
		event.EventID = "billing_evt_" + payloadFingerprint[:16]
	}
	now := repository.now().UTC().Truncate(time.Microsecond)
	event.ReceivedAt = now
	if len(event.Failures) > 0 {
		// Public callers cannot assert verification. Reject before opening a
		// transaction so provider, ledger, quota, entitlement, audit, payment,
		// and idempotency state all remain unchanged.
		return rejectedBillingWebhookEnvelope(event), nil
	}
	requestFingerprint := JSONMap{"tenant_id": tenantID, "project_id": projectID, "event_id": event.EventID, "event_type": event.EventType, "provider": event.Provider, "mode": event.Mode, "payload_sha256": event.PayloadSHA256, "metadata": event.Metadata}
	response := Envelope[BillingWebhookIngest]{Operation: "billing.webhook_ingest", Status: "ok", Result: event}

	ctx := context.Background()
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return Envelope[BillingWebhookIngest]{}, fmt.Errorf("billing webhook begin transaction: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	if options.Key != "" {
		if replay, ok, err := loadIdempotentBillingWebhookReplay(ctx, tx, response.Operation, tenantID, projectID, options.Key, requestFingerprint); err != nil || ok {
			return replay, err
		}
	}
	if err := requireProject(ctx, tx, tenantID, projectID); err != nil {
		return Envelope[BillingWebhookIngest]{}, err
	}
	if err := ensurePostgresBillingSaaSScope(ctx, tx, tenantID, projectID, now); err != nil {
		return Envelope[BillingWebhookIngest]{}, err
	}
	replayStatus, mutationCount, err := ingestPostgresBillingProviderEvent(ctx, tx, tenantID, projectID, event)
	if err != nil {
		return Envelope[BillingWebhookIngest]{}, err
	}
	if replayStatus == "conflict" {
		event.Verified = false
		event.Failures = append(event.Failures, JSONMap{"reason": "provider_event_payload_conflict"})
		response.Status = "conflict"
		response.Result = event
	} else if replayStatus == "duplicate" {
		response.IdempotentReplay = true
	}
	if mutationCount > 0 {
		if err := appendPostgresMutationEvidence(ctx, tx, tenantID, projectID, response.Operation, 1, postgresMutationEvidence{APIKeyID: options.APIKeyID, IdempotencyKey: options.Key, RequestID: options.RequestID, TargetID: event.EventID, After: JSONMap{"event_id": event.EventID, "event_type": event.EventType, "payload_sha256": event.PayloadSHA256, "raw_payload_included": false}}, now); err != nil {
			return Envelope[BillingWebhookIngest]{}, err
		}
	}
	if options.Key != "" {
		if replay, ok, err := insertIdempotentBillingWebhookResponse(ctx, tx, response.Operation, tenantID, projectID, options.Key, requestFingerprint, response); err != nil || ok {
			return replay, err
		}
	}
	if err := tx.Commit(); err != nil {
		return Envelope[BillingWebhookIngest]{}, fmt.Errorf("billing webhook commit: %w", err)
	}
	return response, nil
}

func (repository *PostgresRepository) BillingLedger(tenantID, projectID string) (Envelope[BillingLedger], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[BillingLedger]{}, err
	}
	ctx := context.Background()
	if err := requireProjectWithDB(ctx, repository.db, tenantID, projectID); err != nil {
		return Envelope[BillingLedger]{}, err
	}
	rows, err := repository.db.QueryContext(ctx, `
SELECT p.provider_event_id, p.provider_event_type, p.provider, p.mode, COALESCE(l.customer_ref, ''), COALESCE((l.metadata->>'plan_id'), ''), COALESCE((l.metadata->>'status'), 'received'), p.payload_sha256, p.signature_verified, COALESCE((l.metadata->>'webhook_secret_ref'), ''), COALESCE((l.metadata->>'livemode')::boolean, false), COALESCE(l.metadata, '{}'::jsonb), p.created_at
FROM billing_provider_events p
LEFT JOIN billing_ledger_events l ON l.organization_id = p.organization_id AND l.project_id = p.project_id AND l.provider_event_id = p.id
WHERE p.organization_id = $1::uuid AND p.project_id = $2::uuid
ORDER BY p.created_at ASC, p.provider_event_id ASC
`, postgresBillingUUID("org", tenantID), postgresBillingUUID("project", projectID))
	if err != nil {
		return Envelope[BillingLedger]{}, fmt.Errorf("billing ledger query: %w", err)
	}
	defer rows.Close()
	events := []BillingWebhookIngest{}
	for rows.Next() {
		event, err := scanPostgresBillingLedgerEvent(rows, tenantID, projectID)
		if err != nil {
			return Envelope[BillingLedger]{}, err
		}
		events = append(events, event)
	}
	if err := rows.Err(); err != nil {
		return Envelope[BillingLedger]{}, fmt.Errorf("iterate billing ledger: %w", err)
	}
	result := BillingLedger{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, Events: events, Count: len(events), GeneratedAt: repository.now().UTC()}
	return Envelope[BillingLedger]{Operation: "billing.ledger", Status: "ok", Result: result}, nil
}

func (repository *PostgresRepository) AppendQuotaUsage(tenantID, projectID string, event QuotaUsageAppend) (Envelope[UsageOperationTotal], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[UsageOperationTotal]{}, err
	}
	operation := NormalizeQuotaOperation(event.Operation)
	if operation == "" {
		return Envelope[UsageOperationTotal]{}, fmt.Errorf("quota usage operation is required")
	}
	ctx := context.Background()
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return Envelope[UsageOperationTotal]{}, fmt.Errorf("quota usage append begin transaction: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	now := event.CreatedAt
	if now.IsZero() {
		now = repository.now()
	}
	now = now.UTC().Truncate(time.Microsecond)
	evidence := postgresMutationEvidence{APIKeyID: event.APIKeyID, IdempotencyKey: event.IdempotencyKey, RequestID: event.RequestID, RunID: event.RunID, TargetID: event.TargetID}
	if err := appendPostgresUsageEvent(ctx, tx, tenantID, projectID, operation, quotaUnits(event.Units), evidence, now); err != nil {
		return Envelope[UsageOperationTotal]{}, err
	}
	if err := tx.Commit(); err != nil {
		return Envelope[UsageOperationTotal]{}, fmt.Errorf("quota usage append commit: %w", err)
	}
	snapshot, err := repository.UsageSnapshot(tenantID, projectID)
	if err != nil {
		return Envelope[UsageOperationTotal]{}, err
	}
	for _, total := range snapshot.Result.OperationTotals {
		if total.Operation == operation {
			return Envelope[UsageOperationTotal]{Operation: "quota_usage.append", Status: "ok", Result: total}, nil
		}
	}
	return Envelope[UsageOperationTotal]{Operation: "quota_usage.append", Status: "ok", Result: UsageOperationTotal{Operation: operation}}, nil
}

func (repository *PostgresRepository) mutateLeasedWorkerJob(tenantID, projectID, jobID, leaseOwnerID string, now time.Time, operation string, mutate func(context.Context, *sql.Tx, WorkerJob) (WorkerJob, error)) (Envelope[WorkerJob], error) {
	ctx := context.Background()
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return Envelope[WorkerJob]{}, fmt.Errorf("%s begin transaction: %w", operation, err)
	}
	defer rollbackUnlessCommitted(tx)
	if err := expirePostgresWorkerLeases(ctx, tx, tenantID, projectID, now); err != nil {
		return Envelope[WorkerJob]{}, err
	}
	job, err := loadPostgresWorkerJobForUpdate(ctx, tx, tenantID, projectID, jobID)
	if err != nil {
		return Envelope[WorkerJob]{}, err
	}
	if err := requirePostgresWorkerJobLease(job, leaseOwnerID, now); err != nil {
		return Envelope[WorkerJob]{}, err
	}
	job, err = mutate(ctx, tx, job)
	if err != nil {
		return Envelope[WorkerJob]{}, err
	}
	units := 1
	if operation == "worker.job.heartbeat" {
		units = 0
	}
	if err := appendPostgresMutationEvidence(ctx, tx, tenantID, projectID, operation, units, postgresMutationEvidence{IdempotencyKey: job.IdempotencyKey, RequestID: job.RequestID, RunID: job.TargetID, TargetID: jobID, After: JSONMap{"job_id": jobID, "job_type": job.JobType, "status": job.Status, "attempts": job.Attempts}}, now); err != nil {
		return Envelope[WorkerJob]{}, err
	}
	if err := tx.Commit(); err != nil {
		return Envelope[WorkerJob]{}, fmt.Errorf("%s commit: %w", operation, err)
	}
	return Envelope[WorkerJob]{Operation: operation, Status: "ok", Result: job}, nil
}

func (repository *PostgresRepository) notImplemented(operation string) error {
	return fmt.Errorf("%s: %w", operation, ErrPostgresRepositoryNotImplemented)
}

func (repository *PostgresRepository) CreateAPIKey(tenantID, projectID string, options CreateAPIKeyOptions) (Envelope[APIKeyCreateResult], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[APIKeyCreateResult]{}, err
	}
	if strings.TrimSpace(options.APIKey) != "" {
		return Envelope[APIKeyCreateResult]{}, AuthzError{Code: "secret_input_rejected", Message: "postgres API key lifecycle only generates one-time local test secrets"}
	}
	keyID := strings.TrimSpace(firstNonEmpty(options.KeyID, options.AuthKeyID))
	if keyID == "" {
		keyID = "key_" + mustFingerprint(JSONMap{"tenant_id": tenantID, "project_id": projectID, "name": options.Name, "created_at": repository.now().UnixNano()})[:16]
	}
	if stringHasRawSecretShape(keyID) || stringHasRawSecretShape(options.Name) {
		return Envelope[APIKeyCreateResult]{}, AuthzError{Code: "secret_input_rejected", Message: "api key identifiers and names must not contain raw secret material"}
	}
	scopes := sortedUniqueStrings(options.Scopes)
	if len(scopes) == 0 {
		return Envelope[APIKeyCreateResult]{}, fmt.Errorf("at least one scope is required")
	}
	secret := localAPIKeySecretPrefix + keyID + "_" + mustFingerprint(JSONMap{"tenant_id": tenantID, "project_id": projectID, "key_id": keyID})[:16]
	now := repository.now().UTC().Truncate(time.Microsecond)
	ctx := context.Background()
	record := APIKeyRecord{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, KeyID: keyID, Name: strings.TrimSpace(options.Name), SecretPrefix: secretPrefix(secret), Scopes: scopes, CreatedAt: now}
	if record.Name == "" {
		record.Name = keyID
	}
	if err := repository.upsertPostgresAPIKey(ctx, record, secretHash(secret), "active", nil); err != nil {
		return Envelope[APIKeyCreateResult]{}, err
	}
	result := APIKeyCreateResult{SchemaVersion: ControlPlaneSchemaVersion, APIKey: redactedAPIKeyRecord(record), OneTimeSecretDisplayed: options.RevealSecret}
	if options.RevealSecret {
		result.OneTimeSecret = secret
	}
	return Envelope[APIKeyCreateResult]{Operation: "api_key.create", Status: "ok", Result: result}, nil
}

func (repository *PostgresRepository) ListAPIKeys(tenantID, projectID string) (Envelope[APIKeyListResult], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[APIKeyListResult]{}, err
	}
	localFallback := false
	rows, err := repository.db.QueryContext(context.Background(), `
SELECT id, name, key_prefix, scopes, status, created_at, last_used_at
FROM api_keys
WHERE organization_id::text = $1 AND project_id::text = $2
ORDER BY created_at DESC, id
`, tenantID, projectID)
	if err != nil && !postgresRelationMissing(err) {
		return Envelope[APIKeyListResult]{}, fmt.Errorf("list api keys: %w", err)
	}
	if postgresRelationMissing(err) {
		localFallback = true
		if err := repository.ensureLocalPostgresAPIKeySchema(context.Background()); err != nil {
			return Envelope[APIKeyListResult]{}, err
		}
		rows, err = repository.db.QueryContext(context.Background(), `
SELECT key_id, name, secret_prefix, scopes, revoked, created_at, last_used_at
FROM releasefoundry_api_keys
WHERE tenant_id = $1 AND project_id = $2
ORDER BY created_at DESC, key_id
`, tenantID, projectID)
	}
	if err != nil {
		return Envelope[APIKeyListResult]{}, fmt.Errorf("list api keys: %w", err)
	}
	defer rows.Close()
	keys := make([]APIKeyRecord, 0)
	for rows.Next() {
		var record APIKeyRecord
		if localFallback {
			record, err = scanLocalPostgresAPIKeyRecord(rows, tenantID, projectID)
		} else {
			record, err = scanPostgresAPIKeyRecord(rows, tenantID, projectID)
		}
		if err != nil {
			return Envelope[APIKeyListResult]{}, err
		}
		keys = append(keys, redactedAPIKeyRecord(record))
	}
	if err := rows.Err(); err != nil {
		return Envelope[APIKeyListResult]{}, fmt.Errorf("list api keys rows: %w", err)
	}
	result := APIKeyListResult{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, APIKeys: keys, Count: len(keys)}
	return Envelope[APIKeyListResult]{Operation: "api_key.list", Status: "ok", Result: result}, nil
}

func (repository *PostgresRepository) RevokeAPIKey(tenantID, projectID, keyID string) (Envelope[APIKeyRecord], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[APIKeyRecord]{}, err
	}
	now := repository.now().UTC().Truncate(time.Microsecond)
	ctx := context.Background()
	var result sql.Result
	var err error
	if looksLikeUUID(tenantID) && looksLikeUUID(projectID) && looksLikeUUID(keyID) {
		result, err = repository.db.ExecContext(ctx, `
UPDATE api_keys
SET status = 'revoked', revoked_at = $4, last_used_at = last_used_at
WHERE organization_id::text = $1 AND project_id::text = $2 AND id::text = $3
`, tenantID, projectID, keyID, now)
	}
	if err != nil && !postgresRelationMissing(err) {
		return Envelope[APIKeyRecord]{}, fmt.Errorf("revoke api key: %w", err)
	}
	if result == nil || postgresRelationMissing(err) {
		if err := repository.ensureLocalPostgresAPIKeySchema(ctx); err != nil {
			return Envelope[APIKeyRecord]{}, err
		}
		result, err = repository.db.ExecContext(ctx, `
UPDATE releasefoundry_api_keys
SET revoked = true, revoked_at = $4
WHERE tenant_id = $1 AND project_id = $2 AND key_id = $3
`, tenantID, projectID, keyID, now)
	}
	if err != nil {
		return Envelope[APIKeyRecord]{}, fmt.Errorf("revoke api key: %w", err)
	}
	affected, _ := result.RowsAffected()
	if affected == 0 {
		return Envelope[APIKeyRecord]{}, NotFoundError{Resource: "api key"}
	}
	record, err := repository.loadPostgresAPIKey(ctx, tenantID, projectID, keyID)
	if err != nil {
		return Envelope[APIKeyRecord]{}, err
	}
	return Envelope[APIKeyRecord]{Operation: "api_key.revoke", Status: "ok", Result: redactedAPIKeyRecord(record)}, nil
}

func (repository *PostgresRepository) VerifyAPIKeySecret(tenantID, projectID, keyID, secret, scope string) (Envelope[APIKeyVerifyResult], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[APIKeyVerifyResult]{}, err
	}
	if !strings.HasPrefix(strings.TrimSpace(secret), localAPIKeySecretPrefix) {
		return Envelope[APIKeyVerifyResult]{}, AuthzError{Code: "secret_input_rejected", Message: "postgres verification accepts generated local test secrets only"}
	}
	ctx := context.Background()
	record, storedHash, status, err := repository.loadPostgresAPIKeyWithHash(ctx, tenantID, projectID, keyID)
	if err != nil {
		return Envelope[APIKeyVerifyResult]{}, err
	}
	authenticated := strings.TrimSpace(secret) != "" && secretHash(secret) == storedHash && status == "active" && !record.Revoked && scopeAllowed(record.Scopes, scope)
	if authenticated {
		now := repository.now().UTC().Truncate(time.Microsecond)
		_ = repository.touchPostgresAPIKey(ctx, tenantID, projectID, keyID, now)
		record.LastUsedAt = &now
	}
	result := APIKeyVerifyResult{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, KeyID: keyID, Authenticated: authenticated, Scope: scope, SecretValuePresent: false, APIKey: redactedAPIKeyRecord(record)}
	return Envelope[APIKeyVerifyResult]{Operation: "api_key.verify", Status: "ok", Result: result}, nil
}

func (repository *PostgresRepository) ConfigureAPIKeyRateLimit(tenantID, projectID, keyID, operation string, limit int) (Envelope[APIKeyRateLimit], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[APIKeyRateLimit]{}, err
	}
	if strings.TrimSpace(operation) == "" {
		return Envelope[APIKeyRateLimit]{}, fmt.Errorf("operation is required")
	}
	operation = NormalizeQuotaOperation(operation)
	if limit < 0 {
		return Envelope[APIKeyRateLimit]{}, fmt.Errorf("limit must be non-negative")
	}
	if _, err := repository.loadPostgresAPIKey(context.Background(), tenantID, projectID, keyID); err != nil {
		return Envelope[APIKeyRateLimit]{}, err
	}
	now := repository.now().UTC().Truncate(time.Microsecond)
	if err := repository.ensureLocalPostgresAPIKeyRateLimitSchema(context.Background()); err != nil {
		return Envelope[APIKeyRateLimit]{}, err
	}
	_, err := repository.db.ExecContext(context.Background(), `
INSERT INTO releasefoundry_api_key_rate_limits (tenant_id, project_id, key_id, operation, limit_units, used_units, updated_at)
VALUES ($1, $2, $3, $4, $5, 0, $6)
ON CONFLICT (tenant_id, project_id, key_id, operation)
DO UPDATE SET limit_units = EXCLUDED.limit_units, updated_at = EXCLUDED.updated_at
`, tenantID, projectID, keyID, operation, limit, now)
	if err != nil {
		return Envelope[APIKeyRateLimit]{}, fmt.Errorf("configure api key rate limit: %w", err)
	}
	quota, err := repository.loadPostgresAPIKeyRateLimit(context.Background(), tenantID, projectID, keyID, operation)
	if err != nil {
		return Envelope[APIKeyRateLimit]{}, err
	}
	return Envelope[APIKeyRateLimit]{Operation: "api_key.rate_limit.configure", Status: "ok", Result: quota}, nil
}

func (repository *PostgresRepository) upsertPostgresAPIKey(ctx context.Context, record APIKeyRecord, keyHash, status string, revokedAt *time.Time) error {
	if looksLikeUUID(record.TenantID) && looksLikeUUID(record.ProjectID) && looksLikeUUID(record.KeyID) {
		_, err := repository.db.ExecContext(ctx, `
INSERT INTO api_keys (id, organization_id, project_id, name, key_prefix, key_hash, scopes, status, created_at, revoked_at)
VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9, $10)
`, record.KeyID, record.TenantID, record.ProjectID, record.Name, record.SecretPrefix, keyHash, pq.Array(record.Scopes), status, record.CreatedAt, revokedAt)
		if err != nil && !postgresRelationMissing(err) {
			return fmt.Errorf("insert api key: %w", err)
		}
		if err == nil {
			return nil
		}
	}
	if err := repository.ensureLocalPostgresAPIKeySchema(ctx); err != nil {
		return err
	}
	_, err := repository.db.ExecContext(ctx, `
INSERT INTO releasefoundry_api_keys (tenant_id, project_id, key_id, name, secret_prefix, secret_hash, scopes, revoked, created_at, revoked_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
`, record.TenantID, record.ProjectID, record.KeyID, record.Name, record.SecretPrefix, keyHash, pq.Array(record.Scopes), status != "active", record.CreatedAt, revokedAt)
	if err != nil {
		return fmt.Errorf("insert local api key: %w", err)
	}
	return nil
}

func (repository *PostgresRepository) loadPostgresAPIKey(ctx context.Context, tenantID, projectID, keyID string) (APIKeyRecord, error) {
	record, _, _, err := repository.loadPostgresAPIKeyWithHash(ctx, tenantID, projectID, keyID)
	return record, err
}

func (repository *PostgresRepository) loadPostgresAPIKeyWithHash(ctx context.Context, tenantID, projectID, keyID string) (APIKeyRecord, string, string, error) {
	if looksLikeUUID(tenantID) && looksLikeUUID(projectID) && looksLikeUUID(keyID) {
		row := repository.db.QueryRowContext(ctx, `
SELECT id::text, name, key_prefix, key_hash, scopes, status, created_at, last_used_at
FROM api_keys
WHERE organization_id::text = $1 AND project_id::text = $2 AND id::text = $3
`, tenantID, projectID, keyID)
		record, hash, status, err := scanPostgresAPIKeyRecordWithHash(row, tenantID, projectID)
		if err == nil {
			return record, hash, status, nil
		}
		if err != nil && !postgresRelationMissing(err) && !errors.Is(err, sql.ErrNoRows) {
			return APIKeyRecord{}, "", "", fmt.Errorf("load api key: %w", err)
		}
	}
	if err := repository.ensureLocalPostgresAPIKeySchema(ctx); err != nil {
		return APIKeyRecord{}, "", "", err
	}
	row := repository.db.QueryRowContext(ctx, `
SELECT key_id, name, secret_prefix, secret_hash, scopes, revoked, created_at, last_used_at
FROM releasefoundry_api_keys
WHERE tenant_id = $1 AND project_id = $2 AND key_id = $3
`, tenantID, projectID, keyID)
	record, hash, status, err := scanLocalPostgresAPIKeyRecordWithHash(row, tenantID, projectID)
	if errors.Is(err, sql.ErrNoRows) {
		return APIKeyRecord{}, "", "", NotFoundError{Resource: "api key"}
	}
	if err != nil {
		return APIKeyRecord{}, "", "", fmt.Errorf("load local api key: %w", err)
	}
	return record, hash, status, nil
}

func (repository *PostgresRepository) touchPostgresAPIKey(ctx context.Context, tenantID, projectID, keyID string, now time.Time) error {
	result, err := repository.db.ExecContext(ctx, `
UPDATE api_keys SET last_used_at = $4
WHERE organization_id::text = $1 AND project_id::text = $2 AND id::text = $3
`, tenantID, projectID, keyID, now)
	if err != nil && !postgresRelationMissing(err) {
		return fmt.Errorf("touch api key: %w", err)
	}
	if err == nil {
		if affected, _ := result.RowsAffected(); affected > 0 {
			return nil
		}
	}
	_, err = repository.db.ExecContext(ctx, `
UPDATE releasefoundry_api_keys SET last_used_at = $4
WHERE tenant_id = $1 AND project_id = $2 AND key_id = $3
`, tenantID, projectID, keyID, now)
	if err != nil && !postgresRelationMissing(err) {
		return fmt.Errorf("touch local api key: %w", err)
	}
	return nil
}

func (repository *PostgresRepository) ensureLocalPostgresAPIKeySchema(ctx context.Context) error {
	_, err := repository.db.ExecContext(ctx, `
CREATE TABLE IF NOT EXISTS releasefoundry_api_keys (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    key_id TEXT NOT NULL,
    name TEXT NOT NULL,
    secret_prefix TEXT NOT NULL,
    secret_hash TEXT NOT NULL,
    scopes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    revoked BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, project_id, key_id)
)
`)
	if err != nil {
		return fmt.Errorf("ensure local api key schema: %w", err)
	}
	return nil
}

func (repository *PostgresRepository) ensureLocalPostgresAPIKeyRateLimitSchema(ctx context.Context) error {
	_, err := repository.db.ExecContext(ctx, `
CREATE TABLE IF NOT EXISTS releasefoundry_api_key_rate_limits (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    key_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    limit_units INTEGER NOT NULL,
    used_units INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, key_id, operation)
)
`)
	if err != nil {
		return fmt.Errorf("ensure api key rate limit schema: %w", err)
	}
	return nil
}

type apiKeyScanner interface {
	Scan(dest ...any) error
}

func scanPostgresAPIKeyRecord(scanner apiKeyScanner, tenantID, projectID string) (APIKeyRecord, error) {
	record, _, _, err := scanPostgresAPIKeyRecordWithHash(scanner, tenantID, projectID)
	return record, err
}

func scanPostgresAPIKeyRecordWithHash(scanner apiKeyScanner, tenantID, projectID string) (APIKeyRecord, string, string, error) {
	var keyID, name, prefix, hash, status string
	var scopes []string
	var createdAt time.Time
	var lastUsedAt sql.NullTime
	if err := scanner.Scan(&keyID, &name, &prefix, &hash, pq.Array(&scopes), &status, &createdAt, &lastUsedAt); err != nil {
		return APIKeyRecord{}, "", "", err
	}
	record := APIKeyRecord{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, KeyID: keyID, Name: name, SecretPrefix: prefix, Scopes: sortedUniqueStrings(scopes), Revoked: status != "active", CreatedAt: createdAt}
	if lastUsedAt.Valid {
		record.LastUsedAt = &lastUsedAt.Time
	}
	return record, hash, status, nil
}

func scanLocalPostgresAPIKeyRecordWithHash(scanner apiKeyScanner, tenantID, projectID string) (APIKeyRecord, string, string, error) {
	var keyID, name, prefix, hash string
	var scopes []string
	var revoked bool
	var createdAt time.Time
	var lastUsedAt sql.NullTime
	if err := scanner.Scan(&keyID, &name, &prefix, &hash, pq.Array(&scopes), &revoked, &createdAt, &lastUsedAt); err != nil {
		return APIKeyRecord{}, "", "", err
	}
	status := "active"
	if revoked {
		status = "revoked"
	}
	record := APIKeyRecord{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, KeyID: keyID, Name: name, SecretPrefix: prefix, Scopes: sortedUniqueStrings(scopes), Revoked: revoked, CreatedAt: createdAt}
	if lastUsedAt.Valid {
		record.LastUsedAt = &lastUsedAt.Time
	}
	return record, hash, status, nil
}

func scanLocalPostgresAPIKeyRecord(scanner apiKeyScanner, tenantID, projectID string) (APIKeyRecord, error) {
	var keyID, name, prefix string
	var scopes []string
	var revoked bool
	var createdAt time.Time
	var lastUsedAt sql.NullTime
	if err := scanner.Scan(&keyID, &name, &prefix, pq.Array(&scopes), &revoked, &createdAt, &lastUsedAt); err != nil {
		return APIKeyRecord{}, err
	}
	record := APIKeyRecord{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, KeyID: keyID, Name: name, SecretPrefix: prefix, Scopes: sortedUniqueStrings(scopes), Revoked: revoked, CreatedAt: createdAt}
	if lastUsedAt.Valid {
		record.LastUsedAt = &lastUsedAt.Time
	}
	return record, nil
}

type apiKeyRateLimitScanner interface {
	Scan(dest ...any) error
}

func scanPostgresAPIKeyRateLimit(scanner apiKeyRateLimitScanner) (APIKeyRateLimit, error) {
	quota := APIKeyRateLimit{SchemaVersion: ControlPlaneSchemaVersion}
	if err := scanner.Scan(&quota.TenantID, &quota.ProjectID, &quota.KeyID, &quota.Operation, &quota.Limit, &quota.Used, &quota.UpdatedAt); err != nil {
		return APIKeyRateLimit{}, err
	}
	quota.Remaining = quota.Limit - quota.Used
	if quota.Remaining < 0 {
		quota.Remaining = 0
	}
	return quota, nil
}

func (repository *PostgresRepository) loadPostgresAPIKeyRateLimit(ctx context.Context, tenantID, projectID, keyID, operation string) (APIKeyRateLimit, error) {
	operation = NormalizeQuotaOperation(operation)
	if strings.TrimSpace(keyID) == "" || strings.TrimSpace(operation) == "" {
		return APIKeyRateLimit{}, sql.ErrNoRows
	}
	if err := repository.ensureLocalPostgresAPIKeyRateLimitSchema(ctx); err != nil {
		return APIKeyRateLimit{}, err
	}
	row := repository.db.QueryRowContext(ctx, `
SELECT tenant_id, project_id, key_id, operation, limit_units, used_units, updated_at
FROM releasefoundry_api_key_rate_limits
WHERE tenant_id = $1 AND project_id = $2 AND key_id = $3 AND operation = $4
`, tenantID, projectID, keyID, operation)
	return scanPostgresAPIKeyRateLimit(row)
}

func consumeLocalPostgresAPIKeyRateLimit(ctx context.Context, tx *sql.Tx, tenantID, projectID, keyID, operation string, units int, now time.Time) error {
	operation = NormalizeQuotaOperation(operation)
	if strings.TrimSpace(keyID) == "" || strings.TrimSpace(operation) == "" {
		return nil
	}
	if units <= 0 {
		units = 1
	}
	var limit int
	var used int
	err := tx.QueryRowContext(ctx, `
SELECT limit_units, used_units
FROM releasefoundry_api_key_rate_limits
WHERE tenant_id = $1 AND project_id = $2 AND key_id = $3 AND operation = $4
FOR UPDATE
`, tenantID, projectID, keyID, operation).Scan(&limit, &used)
	if errors.Is(err, sql.ErrNoRows) || postgresRelationMissing(err) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("load api key rate limit for consume: %w", err)
	}
	if limit >= 0 && used+units > limit {
		return QuotaExceededError{Operation: operation, Limit: limit, Used: used, Requested: units}
	}
	_, err = tx.ExecContext(ctx, `
UPDATE releasefoundry_api_key_rate_limits
SET used_units = used_units + $5, updated_at = $6
WHERE tenant_id = $1 AND project_id = $2 AND key_id = $3 AND operation = $4
`, tenantID, projectID, keyID, operation, units, now)
	if err != nil {
		return fmt.Errorf("consume api key rate limit: %w", err)
	}
	if looksLikeUUID(tenantID) && looksLikeUUID(projectID) && looksLikeUUID(keyID) {
		if _, err := tx.ExecContext(ctx, `
UPDATE api_keys SET last_used_at = $4
WHERE organization_id::text = $1 AND project_id::text = $2 AND id::text = $3
`, tenantID, projectID, keyID, now); err != nil && !postgresRelationMissing(err) {
			return fmt.Errorf("touch api key after consume: %w", err)
		}
	}
	if _, err := tx.ExecContext(ctx, `
UPDATE releasefoundry_api_keys SET last_used_at = $4
WHERE tenant_id = $1 AND project_id = $2 AND key_id = $3
`, tenantID, projectID, keyID, now); err != nil && !postgresRelationMissing(err) {
		return fmt.Errorf("touch local api key after consume: %w", err)
	}
	return nil
}

func (repository *PostgresRepository) ConfigureUsageQuota(tenantID, projectID, operation string, limit int) (Envelope[UsageOperationTotal], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[UsageOperationTotal]{}, err
	}
	operation = NormalizeQuotaOperation(operation)
	if operation == "" {
		return Envelope[UsageOperationTotal]{}, fmt.Errorf("usage quota operation is required")
	}
	meter, ok := OperationMeterFor(operation)
	if !ok {
		return Envelope[UsageOperationTotal]{}, fmt.Errorf("usage quota operation %q is not supported", operation)
	}
	if limit < 0 {
		return Envelope[UsageOperationTotal]{}, fmt.Errorf("usage quota limit must be non-negative")
	}
	ctx := context.Background()
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return Envelope[UsageOperationTotal]{}, fmt.Errorf("configure usage quota begin transaction: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	now := repository.now().UTC().Truncate(time.Microsecond)
	configuredSaaS, err := configureSaaSUsageQuotaPolicy(ctx, tx, tenantID, projectID, meter, limit, now)
	if err != nil {
		return Envelope[UsageOperationTotal]{}, err
	}
	if !configuredSaaS {
		if err := requireProject(ctx, tx, tenantID, projectID); err != nil {
			return Envelope[UsageOperationTotal]{}, err
		}
		if _, err := tx.ExecContext(ctx, `
INSERT INTO releasefoundry_usage_quota_policies (tenant_id, project_id, operation, meter, limit_units, status, created_at, updated_at)
VALUES ($1, $2, $3, $4, $5, 'active', $6, $6)
ON CONFLICT (tenant_id, project_id, operation)
DO UPDATE SET meter = EXCLUDED.meter, limit_units = EXCLUDED.limit_units, status = 'active', updated_at = EXCLUDED.updated_at
`, tenantID, projectID, operation, meter.Meter, limit, now); err != nil {
			return Envelope[UsageOperationTotal]{}, fmt.Errorf("configure usage quota policy: %w", err)
		}
	}
	if err := tx.Commit(); err != nil {
		return Envelope[UsageOperationTotal]{}, fmt.Errorf("configure usage quota commit: %w", err)
	}
	used, events, err := repository.usageOperationTotal(tenantID, projectID, operation)
	if err != nil {
		return Envelope[UsageOperationTotal]{}, err
	}
	result := UsageOperationTotal{Operation: operation, Units: used, Events: events}
	return Envelope[UsageOperationTotal]{Operation: "usage_quota.configure", Status: "ok", Result: result}, nil
}

func (repository *PostgresRepository) APIKeyRateLimitSnapshot(tenantID, projectID, keyID string) (Envelope[APIKeyRateLimitSnapshot], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[APIKeyRateLimitSnapshot]{}, err
	}
	if err := repository.ensureLocalPostgresAPIKeyRateLimitSchema(context.Background()); err != nil {
		return Envelope[APIKeyRateLimitSnapshot]{}, err
	}
	args := []any{tenantID, projectID}
	where := "tenant_id = $1 AND project_id = $2"
	if strings.TrimSpace(keyID) != "" {
		where += " AND key_id = $3"
		args = append(args, keyID)
	}
	rows, err := repository.db.QueryContext(context.Background(), `
SELECT tenant_id, project_id, key_id, operation, limit_units, used_units, updated_at
FROM releasefoundry_api_key_rate_limits
WHERE `+where+`
ORDER BY key_id, operation
`, args...)
	if err != nil {
		return Envelope[APIKeyRateLimitSnapshot]{}, fmt.Errorf("api key rate limit snapshot: %w", err)
	}
	defer rows.Close()
	limits := make([]APIKeyRateLimit, 0)
	for rows.Next() {
		quota, err := scanPostgresAPIKeyRateLimit(rows)
		if err != nil {
			return Envelope[APIKeyRateLimitSnapshot]{}, err
		}
		limits = append(limits, quota)
	}
	if err := rows.Err(); err != nil {
		return Envelope[APIKeyRateLimitSnapshot]{}, fmt.Errorf("api key rate limit snapshot rows: %w", err)
	}
	result := APIKeyRateLimitSnapshot{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, KeyID: keyID, RateLimits: limits, Count: len(limits)}
	return Envelope[APIKeyRateLimitSnapshot]{Operation: "api_key.rate_limit.snapshot", Status: "ok", Result: result}, nil
}

func (repository *PostgresRepository) PreflightAPIKey(options PreflightOptions) (Envelope[AuthPreflight], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[AuthPreflight]{}, err
	}
	now := repository.now().UTC().Truncate(time.Microsecond)
	units := options.Units
	if units <= 0 {
		units = 1
	}
	result := AuthPreflight{SchemaVersion: ControlPlaneSchemaVersion, TenantID: options.TenantID, ProjectID: options.ProjectID, KeyID: options.KeyID, Scope: options.Scope, Operation: options.Operation, CheckedAt: now}
	record, err := repository.loadPostgresAPIKey(context.Background(), options.TenantID, options.ProjectID, options.KeyID)
	if err != nil {
		return Envelope[AuthPreflight]{Operation: "api_key.preflight", Status: "ok", Result: result}, err
	}
	result.Scopes = append([]string(nil), record.Scopes...)
	if record.Revoked {
		return Envelope[AuthPreflight]{Operation: "api_key.preflight", Status: "ok", Result: result}, AuthzError{Code: "api_key_revoked", Message: "api key handle has been revoked"}
	}
	if !scopeAllowed(record.Scopes, options.Scope) {
		return Envelope[AuthPreflight]{Operation: "api_key.preflight", Status: "ok", Result: result}, AuthzError{Code: "scope_denied", Message: "api key handle does not grant required scope"}
	}
	normalizedOperation := NormalizeQuotaOperation(options.Operation)
	quota, err := repository.loadPostgresAPIKeyRateLimit(context.Background(), options.TenantID, options.ProjectID, options.KeyID, normalizedOperation)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return Envelope[AuthPreflight]{}, err
	}
	if err == nil {
		quota.Remaining = quota.Limit - quota.Used
		if quota.Remaining < 0 {
			quota.Remaining = 0
		}
		result.Quota = &quota
		if quota.Limit >= 0 && quota.Used+units > quota.Limit {
			return Envelope[AuthPreflight]{Operation: "api_key.preflight", Status: "ok", Result: result}, QuotaExceededError{Operation: normalizedOperation, Limit: quota.Limit, Used: quota.Used, Requested: units}
		}
	}
	result.Allowed = true
	return Envelope[AuthPreflight]{Operation: "api_key.preflight", Status: "ok", Result: result}, nil
}

func (repository *PostgresRepository) requireDB() error {
	if repository == nil || repository.db == nil {
		return fmt.Errorf("postgres repository db is required")
	}
	return nil
}

func upsertTenant(ctx context.Context, tx *sql.Tx, tenant Tenant) error {
	metadata, err := jsonBytes(defaultMap(tenant.Metadata))
	if err != nil {
		return fmt.Errorf("marshal tenant metadata: %w", err)
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO releasefoundry_tenants (tenant_id, name, metadata)
VALUES ($1, $2, $3::jsonb)
ON CONFLICT (tenant_id) DO UPDATE SET name = EXCLUDED.name, metadata = EXCLUDED.metadata, updated_at = now()
`, tenant.TenantID, tenant.Name, string(metadata))
	if err != nil {
		return fmt.Errorf("upsert tenant: %w", err)
	}
	return nil
}

func upsertProject(ctx context.Context, tx *sql.Tx, project Project) error {
	metadata, err := jsonBytes(defaultMap(project.Metadata))
	if err != nil {
		return fmt.Errorf("marshal project metadata: %w", err)
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO releasefoundry_projects (tenant_id, project_id, name, metadata)
VALUES ($1, $2, $3, $4::jsonb)
ON CONFLICT (tenant_id, project_id) DO UPDATE SET name = EXCLUDED.name, metadata = EXCLUDED.metadata, updated_at = now()
`, project.TenantID, project.ProjectID, project.Name, string(metadata))
	if err != nil {
		return fmt.Errorf("upsert project: %w", err)
	}
	return nil
}

func upsertDataset(ctx context.Context, tx *sql.Tx, dataset Dataset) error {
	cases, err := jsonBytes(defaultCases(dataset.Cases))
	if err != nil {
		return fmt.Errorf("marshal dataset cases: %w", err)
	}
	metadata, err := jsonBytes(defaultMap(dataset.Metadata))
	if err != nil {
		return fmt.Errorf("marshal dataset metadata: %w", err)
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO releasefoundry_datasets (tenant_id, project_id, dataset_id, name, cases, metadata)
VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
ON CONFLICT (tenant_id, project_id, dataset_id) DO UPDATE SET name = EXCLUDED.name, cases = EXCLUDED.cases, metadata = EXCLUDED.metadata, updated_at = now()
`, dataset.TenantID, dataset.ProjectID, dataset.DatasetID, dataset.Name, string(cases), string(metadata))
	if err != nil {
		return fmt.Errorf("upsert dataset: %w", err)
	}
	return nil
}

func upsertRun(ctx context.Context, tx *sql.Tx, run Run) error {
	metadata, err := jsonBytes(defaultMap(run.Metadata))
	if err != nil {
		return fmt.Errorf("marshal run metadata: %w", err)
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO releasefoundry_runs (tenant_id, project_id, run_id, dataset_id, agent_ref, status, metadata)
VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
ON CONFLICT (tenant_id, project_id, run_id) DO UPDATE SET dataset_id = EXCLUDED.dataset_id, agent_ref = EXCLUDED.agent_ref, status = EXCLUDED.status, metadata = EXCLUDED.metadata, updated_at = now()
`, run.TenantID, run.ProjectID, run.RunID, run.DatasetID, run.AgentRef, run.Status, string(metadata))
	if err != nil {
		return fmt.Errorf("upsert run: %w", err)
	}
	return nil
}

func loadIdempotentRunReplay(ctx context.Context, tx *sql.Tx, operation, tenantID, projectID, key string, request any) (Envelope[Run], bool, error) {
	var storedFingerprint string
	var responsePayload []byte
	err := tx.QueryRowContext(ctx, `
SELECT request_fingerprint, response_json
FROM releasefoundry_idempotency_ledger
WHERE operation = $1 AND tenant_id = $2 AND project_id = $3 AND key = $4
`, operation, tenantID, projectID, key).Scan(&storedFingerprint, &responsePayload)
	if errors.Is(err, sql.ErrNoRows) {
		return Envelope[Run]{}, false, nil
	}
	if err != nil {
		return Envelope[Run]{}, false, fmt.Errorf("load idempotency ledger: %w", err)
	}
	requestFingerprint, err := fingerprint(request)
	if err != nil {
		return Envelope[Run]{}, false, err
	}
	if storedFingerprint != requestFingerprint {
		return Envelope[Run]{}, false, IdempotencyConflictError{Operation: operation, Key: key}
	}
	var replay Envelope[Run]
	if err := json.Unmarshal(responsePayload, &replay); err != nil {
		return Envelope[Run]{}, false, fmt.Errorf("decode idempotency response: %w", err)
	}
	replay.IdempotentReplay = true
	return replay, true, nil
}

func insertIdempotentRunResponse(ctx context.Context, tx *sql.Tx, operation, tenantID, projectID, key string, request any, response Envelope[Run]) (Envelope[Run], bool, error) {
	requestFingerprint, err := fingerprint(request)
	if err != nil {
		return Envelope[Run]{}, false, err
	}
	responsePayload, err := jsonBytes(response)
	if err != nil {
		return Envelope[Run]{}, false, fmt.Errorf("marshal idempotency response: %w", err)
	}
	result, err := tx.ExecContext(ctx, `
INSERT INTO releasefoundry_idempotency_ledger (operation, tenant_id, project_id, key, request_fingerprint, response_json)
VALUES ($1, $2, $3, $4, $5, $6::jsonb)
ON CONFLICT (operation, tenant_id, project_id, key) DO NOTHING
`, operation, tenantID, projectID, key, requestFingerprint, string(responsePayload))
	if err != nil {
		return Envelope[Run]{}, false, fmt.Errorf("insert idempotency ledger: %w", err)
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil || rowsAffected > 0 {
		return Envelope[Run]{}, false, nil
	}
	return loadIdempotentRunReplay(ctx, tx, operation, tenantID, projectID, key, request)
}

func loadIdempotentWorkerJobReplay(ctx context.Context, tx *sql.Tx, operation, tenantID, projectID, key string, request any) (Envelope[WorkerJob], bool, error) {
	var storedFingerprint string
	var responsePayload []byte
	err := tx.QueryRowContext(ctx, `
SELECT request_fingerprint, response_json
FROM releasefoundry_idempotency_ledger
WHERE operation = $1 AND tenant_id = $2 AND project_id = $3 AND key = $4
`, operation, tenantID, projectID, key).Scan(&storedFingerprint, &responsePayload)
	if errors.Is(err, sql.ErrNoRows) {
		return Envelope[WorkerJob]{}, false, nil
	}
	if err != nil {
		return Envelope[WorkerJob]{}, false, fmt.Errorf("load worker idempotency ledger: %w", err)
	}
	requestFingerprint, err := fingerprint(request)
	if err != nil {
		return Envelope[WorkerJob]{}, false, err
	}
	if storedFingerprint != requestFingerprint {
		return Envelope[WorkerJob]{}, false, IdempotencyConflictError{Operation: operation, Key: key}
	}
	var replay Envelope[WorkerJob]
	if err := json.Unmarshal(responsePayload, &replay); err != nil {
		return Envelope[WorkerJob]{}, false, fmt.Errorf("decode worker idempotency response: %w", err)
	}
	replay.IdempotentReplay = true
	return replay, true, nil
}

func insertIdempotentWorkerJobResponse(ctx context.Context, tx *sql.Tx, operation, tenantID, projectID, key string, request any, response Envelope[WorkerJob]) (Envelope[WorkerJob], bool, error) {
	requestFingerprint, err := fingerprint(request)
	if err != nil {
		return Envelope[WorkerJob]{}, false, err
	}
	responsePayload, err := jsonBytes(response)
	if err != nil {
		return Envelope[WorkerJob]{}, false, fmt.Errorf("marshal worker idempotency response: %w", err)
	}
	result, err := tx.ExecContext(ctx, `
INSERT INTO releasefoundry_idempotency_ledger (operation, tenant_id, project_id, key, request_fingerprint, response_json)
VALUES ($1, $2, $3, $4, $5, $6::jsonb)
ON CONFLICT (operation, tenant_id, project_id, key) DO NOTHING
`, operation, tenantID, projectID, key, requestFingerprint, string(responsePayload))
	if err != nil {
		return Envelope[WorkerJob]{}, false, fmt.Errorf("insert worker idempotency ledger: %w", err)
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil || rowsAffected > 0 {
		return Envelope[WorkerJob]{}, false, nil
	}
	return loadIdempotentWorkerJobReplay(ctx, tx, operation, tenantID, projectID, key, request)
}

func loadIdempotentRunUploadReplay(ctx context.Context, tx *sql.Tx, operation, tenantID, projectID, key string, request any) (Envelope[RunUpload], bool, error) {
	var storedFingerprint string
	var responsePayload []byte
	err := tx.QueryRowContext(ctx, `
SELECT request_fingerprint, response_json
FROM releasefoundry_idempotency_ledger
WHERE operation = $1 AND tenant_id = $2 AND project_id = $3 AND key = $4
`, operation, tenantID, projectID, key).Scan(&storedFingerprint, &responsePayload)
	if errors.Is(err, sql.ErrNoRows) {
		return Envelope[RunUpload]{}, false, nil
	}
	if err != nil {
		return Envelope[RunUpload]{}, false, fmt.Errorf("load upload idempotency ledger: %w", err)
	}
	requestFingerprint, err := fingerprint(request)
	if err != nil {
		return Envelope[RunUpload]{}, false, err
	}
	if storedFingerprint != requestFingerprint {
		return Envelope[RunUpload]{}, false, IdempotencyConflictError{Operation: operation, Key: key}
	}
	var replay Envelope[RunUpload]
	if err := json.Unmarshal(responsePayload, &replay); err != nil {
		return Envelope[RunUpload]{}, false, fmt.Errorf("decode upload idempotency response: %w", err)
	}
	replay.IdempotentReplay = true
	return replay, true, nil
}

func insertIdempotentRunUploadResponse(ctx context.Context, tx *sql.Tx, operation, tenantID, projectID, key string, request any, response Envelope[RunUpload]) (Envelope[RunUpload], bool, error) {
	requestFingerprint, err := fingerprint(request)
	if err != nil {
		return Envelope[RunUpload]{}, false, err
	}
	responsePayload, err := jsonBytes(response)
	if err != nil {
		return Envelope[RunUpload]{}, false, fmt.Errorf("marshal upload idempotency response: %w", err)
	}
	result, err := tx.ExecContext(ctx, `
INSERT INTO releasefoundry_idempotency_ledger (operation, tenant_id, project_id, key, request_fingerprint, response_json)
VALUES ($1, $2, $3, $4, $5, $6::jsonb)
ON CONFLICT (operation, tenant_id, project_id, key) DO NOTHING
`, operation, tenantID, projectID, key, requestFingerprint, string(responsePayload))
	if err != nil {
		return Envelope[RunUpload]{}, false, fmt.Errorf("insert upload idempotency ledger: %w", err)
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil || rowsAffected > 0 {
		return Envelope[RunUpload]{}, false, nil
	}
	return loadIdempotentRunUploadReplay(ctx, tx, operation, tenantID, projectID, key, request)
}

func loadIdempotentTraceBatchReplay(ctx context.Context, tx *sql.Tx, operation, tenantID, projectID, key string, request any) (Envelope[TraceBatch], bool, error) {
	var storedFingerprint string
	var responsePayload []byte
	err := tx.QueryRowContext(ctx, `
SELECT request_fingerprint, response_json
FROM releasefoundry_idempotency_ledger
WHERE operation = $1 AND tenant_id = $2 AND project_id = $3 AND key = $4
`, operation, tenantID, projectID, key).Scan(&storedFingerprint, &responsePayload)
	if errors.Is(err, sql.ErrNoRows) {
		return Envelope[TraceBatch]{}, false, nil
	}
	if err != nil {
		return Envelope[TraceBatch]{}, false, fmt.Errorf("load trace idempotency ledger: %w", err)
	}
	requestFingerprint, err := fingerprint(request)
	if err != nil {
		return Envelope[TraceBatch]{}, false, err
	}
	if storedFingerprint != requestFingerprint {
		return Envelope[TraceBatch]{}, false, IdempotencyConflictError{Operation: operation, Key: key}
	}
	var replay Envelope[TraceBatch]
	if err := json.Unmarshal(responsePayload, &replay); err != nil {
		return Envelope[TraceBatch]{}, false, fmt.Errorf("decode trace idempotency response: %w", err)
	}
	replay.IdempotentReplay = true
	return replay, true, nil
}

func insertIdempotentTraceBatchResponse(ctx context.Context, tx *sql.Tx, operation, tenantID, projectID, key string, request any, response Envelope[TraceBatch]) (Envelope[TraceBatch], bool, error) {
	requestFingerprint, err := fingerprint(request)
	if err != nil {
		return Envelope[TraceBatch]{}, false, err
	}
	responsePayload, err := jsonBytes(response)
	if err != nil {
		return Envelope[TraceBatch]{}, false, fmt.Errorf("marshal trace idempotency response: %w", err)
	}
	result, err := tx.ExecContext(ctx, `
INSERT INTO releasefoundry_idempotency_ledger (operation, tenant_id, project_id, key, request_fingerprint, response_json)
VALUES ($1, $2, $3, $4, $5, $6::jsonb)
ON CONFLICT (operation, tenant_id, project_id, key) DO NOTHING
`, operation, tenantID, projectID, key, requestFingerprint, string(responsePayload))
	if err != nil {
		return Envelope[TraceBatch]{}, false, fmt.Errorf("insert trace idempotency ledger: %w", err)
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil || rowsAffected > 0 {
		return Envelope[TraceBatch]{}, false, nil
	}
	return loadIdempotentTraceBatchReplay(ctx, tx, operation, tenantID, projectID, key, request)
}

func loadIdempotentArtifactManifestReplay(ctx context.Context, tx *sql.Tx, operation, tenantID, projectID, key string, request any) (Envelope[ArtifactManifest], bool, error) {
	var storedFingerprint string
	var responsePayload []byte
	err := tx.QueryRowContext(ctx, `
SELECT request_fingerprint, response_json
FROM releasefoundry_idempotency_ledger
WHERE operation = $1 AND tenant_id = $2 AND project_id = $3 AND key = $4
`, operation, tenantID, projectID, key).Scan(&storedFingerprint, &responsePayload)
	if errors.Is(err, sql.ErrNoRows) {
		return Envelope[ArtifactManifest]{}, false, nil
	}
	if err != nil {
		return Envelope[ArtifactManifest]{}, false, fmt.Errorf("load artifact idempotency ledger: %w", err)
	}
	requestFingerprint, err := fingerprint(request)
	if err != nil {
		return Envelope[ArtifactManifest]{}, false, err
	}
	if storedFingerprint != requestFingerprint {
		return Envelope[ArtifactManifest]{}, false, IdempotencyConflictError{Operation: operation, Key: key}
	}
	var replay Envelope[ArtifactManifest]
	if err := json.Unmarshal(responsePayload, &replay); err != nil {
		return Envelope[ArtifactManifest]{}, false, fmt.Errorf("decode artifact idempotency response: %w", err)
	}
	replay.IdempotentReplay = true
	return replay, true, nil
}

func insertIdempotentArtifactManifestResponse(ctx context.Context, tx *sql.Tx, operation, tenantID, projectID, key string, request any, response Envelope[ArtifactManifest]) (Envelope[ArtifactManifest], bool, error) {
	requestFingerprint, err := fingerprint(request)
	if err != nil {
		return Envelope[ArtifactManifest]{}, false, err
	}
	responsePayload, err := jsonBytes(response)
	if err != nil {
		return Envelope[ArtifactManifest]{}, false, fmt.Errorf("marshal artifact idempotency response: %w", err)
	}
	result, err := tx.ExecContext(ctx, `
INSERT INTO releasefoundry_idempotency_ledger (operation, tenant_id, project_id, key, request_fingerprint, response_json)
VALUES ($1, $2, $3, $4, $5, $6::jsonb)
ON CONFLICT (operation, tenant_id, project_id, key) DO NOTHING
`, operation, tenantID, projectID, key, requestFingerprint, string(responsePayload))
	if err != nil {
		return Envelope[ArtifactManifest]{}, false, fmt.Errorf("insert artifact idempotency ledger: %w", err)
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil || rowsAffected > 0 {
		return Envelope[ArtifactManifest]{}, false, nil
	}
	return loadIdempotentArtifactManifestReplay(ctx, tx, operation, tenantID, projectID, key, request)
}

func insertPostgresBillingCheckoutPlan(ctx context.Context, tx *sql.Tx, result BillingCheckoutPlan, options IdempotencyOptions) error {
	providerConfig, err := jsonBytes(defaultMap(result.ProviderConfig))
	if err != nil {
		return fmt.Errorf("marshal checkout provider config: %w", err)
	}
	price, err := jsonBytes(defaultMap(result.Price))
	if err != nil {
		return fmt.Errorf("marshal checkout price: %w", err)
	}
	metadata, err := jsonBytes(defaultMap(result.Metadata))
	if err != nil {
		return fmt.Errorf("marshal checkout metadata: %w", err)
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO releasefoundry_billing_checkout_plans (tenant_id, project_id, checkout_id, plan_id, billing_cycle, provider, mode, customer_ref, checkout_url, price, provider_config, metadata, success_url, cancel_url, idempotency_key, request_id, api_key_id, provider_called, real_charge_possible, raw_payload_included, raw_secrets_included, secret_value_present, created_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11::jsonb, $12::jsonb, $13, $14, $15, $16, $17, false, false, false, false, false, $18)
ON CONFLICT (tenant_id, project_id, checkout_id) DO NOTHING
`, result.TenantID, result.ProjectID, result.CheckoutID, result.PlanID, result.BillingCycle, result.Provider, result.Mode, result.CustomerRef, result.CheckoutURL, string(price), string(providerConfig), string(metadata), result.SuccessURL, result.CancelURL, options.Key, options.RequestID, options.APIKeyID, result.CreatedAt)
	if err != nil {
		return fmt.Errorf("insert billing checkout plan: %w", err)
	}
	return nil
}

func insertPostgresBillingPortalPlan(ctx context.Context, tx *sql.Tx, result BillingPortalPlan, options IdempotencyOptions) error {
	providerConfig, err := jsonBytes(defaultMap(result.ProviderConfig))
	if err != nil {
		return fmt.Errorf("marshal portal provider config: %w", err)
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO releasefoundry_billing_portal_plans (tenant_id, project_id, portal_session_id, plan_id, provider, mode, customer_ref, portal_url, provider_config, return_url, idempotency_key, request_id, api_key_id, provider_called, real_charge_possible, raw_payload_included, raw_secrets_included, secret_value_present, created_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12, $13, false, false, false, false, false, $14)
ON CONFLICT (tenant_id, project_id, portal_session_id) DO NOTHING
`, result.TenantID, result.ProjectID, result.PortalSessionID, result.PlanID, result.Provider, result.Mode, result.CustomerRef, result.PortalURL, string(providerConfig), result.ReturnURL, options.Key, options.RequestID, options.APIKeyID, result.CreatedAt)
	if err != nil {
		return fmt.Errorf("insert billing portal plan: %w", err)
	}
	return nil
}

func ensurePostgresBillingSaaSScope(ctx context.Context, tx *sql.Tx, tenantID, projectID string, now time.Time) error {
	orgID := postgresBillingUUID("org", tenantID)
	workspaceID := postgresBillingUUID("workspace", tenantID+":"+projectID)
	saasProjectID := postgresBillingUUID("project", projectID)
	metadata, err := jsonBytes(JSONMap{"source": "go-postgres-billing", "tenant_id": tenantID, "project_id": projectID, "raw_payload_included": false, "secret_value_present": false})
	if err != nil {
		return fmt.Errorf("marshal billing SaaS scope metadata: %w", err)
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO organizations (id, slug, display_name, status, metadata, created_at, updated_at)
VALUES ($1::uuid, $2, $3, 'active', $4::jsonb, $5, $5)
ON CONFLICT (id) DO UPDATE SET slug = EXCLUDED.slug, display_name = EXCLUDED.display_name, updated_at = EXCLUDED.updated_at
`, orgID, postgresSlug(tenantID, "tenant"), tenantID, string(metadata), now)
	if postgresRelationMissing(err) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("ensure billing organization scope: %w", err)
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO workspaces (id, organization_id, slug, display_name, status, metadata, created_at, updated_at)
VALUES ($1::uuid, $2::uuid, $3, $4, 'active', $5::jsonb, $6, $6)
ON CONFLICT (organization_id, id) DO UPDATE SET slug = EXCLUDED.slug, display_name = EXCLUDED.display_name, updated_at = EXCLUDED.updated_at
`, workspaceID, orgID, postgresSlug(projectID, "workspace"), projectID, string(metadata), now)
	if err != nil {
		return fmt.Errorf("ensure billing workspace scope: %w", err)
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO projects (id, organization_id, workspace_id, slug, display_name, status, metadata, created_at, updated_at)
VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, 'active', $6::jsonb, $7, $7)
ON CONFLICT (organization_id, id) DO UPDATE SET workspace_id = EXCLUDED.workspace_id, slug = EXCLUDED.slug, display_name = EXCLUDED.display_name, updated_at = EXCLUDED.updated_at
`, saasProjectID, orgID, workspaceID, postgresSlug(projectID, "project"), projectID, string(metadata), now)
	if err != nil {
		return fmt.Errorf("ensure billing project scope: %w", err)
	}
	return nil
}
func ingestPostgresBillingProviderEvent(ctx context.Context, tx *sql.Tx, tenantID, projectID string, event BillingWebhookIngest) (string, int, error) {
	if !event.Verified {
		return "", 0, fmt.Errorf("billing webhook provider event persistence requires trusted verification")
	}
	metadata := defaultMap(event.Metadata)
	metadata["plan_id"] = event.PlanID
	metadata["status"] = event.Status
	metadata["signature_header_present"] = event.SignatureHeaderPresent
	metadata["webhook_secret_ref"] = event.WebhookSecretRef
	metadata["livemode"] = event.Livemode
	metadata["raw_payload_included"] = false
	metadata["secret_value_present"] = false
	metadataJSON, err := jsonBytes(sanitizedBillingMetadata(metadata))
	if err != nil {
		return "", 0, fmt.Errorf("marshal billing webhook metadata: %w", err)
	}
	var replayStatus string
	var providerEventID string
	var ledgerEventID string
	var mutationCount int
	err = tx.QueryRowContext(ctx, `
SELECT replay_status, provider_event_row_id::text, COALESCE(ledger_event_row_id::text, ''), ledger_mutation_count
FROM ingest_billing_provider_event($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9, NULL, 0, 'usd', 0, $10::jsonb)
`, postgresBillingUUID("org", tenantID), postgresBillingUUID("project", projectID), event.Provider, event.Mode, event.EventID, event.EventType, event.PayloadSHA256, event.Verified, event.CustomerRef, string(metadataJSON)).Scan(&replayStatus, &providerEventID, &ledgerEventID, &mutationCount)
	if err != nil {
		return "", 0, fmt.Errorf("ingest billing provider event: %w", err)
	}
	return replayStatus, mutationCount, nil
}

func scanPostgresBillingLedgerEvent(rows *sql.Rows, tenantID, projectID string) (BillingWebhookIngest, error) {
	var event BillingWebhookIngest
	var metadataPayload []byte
	if err := rows.Scan(&event.EventID, &event.EventType, &event.Provider, &event.Mode, &event.CustomerRef, &event.PlanID, &event.Status, &event.PayloadSHA256, &event.Verified, &event.WebhookSecretRef, &event.Livemode, &metadataPayload, &event.ReceivedAt); err != nil {
		return BillingWebhookIngest{}, fmt.Errorf("scan billing ledger event: %w", err)
	}
	metadata, err := jsonMapFromBytes(metadataPayload)
	if err != nil {
		return BillingWebhookIngest{}, fmt.Errorf("decode billing ledger metadata: %w", err)
	}
	event.SchemaVersion = ControlPlaneSchemaVersion
	event.TenantID = tenantID
	event.ProjectID = projectID
	event.Metadata = sanitizedBillingMetadata(metadata)
	event.SignatureHeaderPresent = boolFromAny(metadata["signature_header_present"])
	event.RawPayloadIncluded = false
	event.SecretValuePresent = false
	event.Failures = billingWebhookFailures(event)
	if !event.Verified && len(event.Failures) == 0 {
		event.Failures = append(event.Failures, JSONMap{"reason": "signature_not_verified"})
	}
	return event, nil
}

func looksLikeSHA256Hex(value string) bool {
	value = strings.TrimSpace(value)
	if len(value) != 64 {
		return false
	}
	for _, char := range value {
		if !((char >= '0' && char <= '9') || (char >= 'a' && char <= 'f')) {
			return false
		}
	}
	return true
}

func postgresSlug(value, fallback string) string {
	value = strings.ToLower(strings.TrimSpace(value))
	builder := strings.Builder{}
	lastDash := false
	for _, char := range value {
		valid := (char >= 'a' && char <= 'z') || (char >= '0' && char <= '9')
		if valid {
			builder.WriteRune(char)
			lastDash = false
			continue
		}
		if !lastDash && builder.Len() > 0 {
			builder.WriteByte('-')
			lastDash = true
		}
	}
	slug := strings.Trim(builder.String(), "-")
	if slug == "" {
		slug = fallback
	}
	if len(slug) > 48 {
		slug = strings.Trim(slug[:48], "-")
	}
	return slug
}
func postgresBillingUUID(prefix, value string) string {
	if looksLikeUUID(value) {
		return strings.ToLower(strings.TrimSpace(value))
	}
	digest := mustFingerprint(JSONMap{"prefix": prefix, "value": strings.TrimSpace(value)})
	return fmt.Sprintf("%s-%s-%s-%s-%s", digest[:8], digest[8:12], digest[12:16], digest[16:20], digest[20:32])
}

func jsonMapFromBytes(payload []byte) (JSONMap, error) {
	if len(payload) == 0 {
		return JSONMap{}, nil
	}
	var decoded map[string]any
	if err := json.Unmarshal(payload, &decoded); err != nil {
		return nil, err
	}
	return cloneMap(JSONMap(decoded)), nil
}

func boolFromAny(value any) bool {
	typed, ok := value.(bool)
	return ok && typed
}

func loadIdempotentBillingCheckoutPlanReplay(ctx context.Context, tx *sql.Tx, operation, tenantID, projectID, key string, request any) (Envelope[BillingCheckoutPlan], bool, error) {
	var storedFingerprint string
	var responsePayload []byte
	err := tx.QueryRowContext(ctx, `
SELECT request_fingerprint, response_json
FROM releasefoundry_idempotency_ledger
WHERE operation = $1 AND tenant_id = $2 AND project_id = $3 AND key = $4
`, operation, tenantID, projectID, key).Scan(&storedFingerprint, &responsePayload)
	if errors.Is(err, sql.ErrNoRows) {
		return Envelope[BillingCheckoutPlan]{}, false, nil
	}
	if err != nil {
		return Envelope[BillingCheckoutPlan]{}, false, fmt.Errorf("load billing checkout idempotency ledger: %w", err)
	}
	requestFingerprint, err := fingerprint(request)
	if err != nil {
		return Envelope[BillingCheckoutPlan]{}, false, err
	}
	if storedFingerprint != requestFingerprint {
		return Envelope[BillingCheckoutPlan]{}, false, IdempotencyConflictError{Operation: operation, Key: key}
	}
	var replay Envelope[BillingCheckoutPlan]
	if err := json.Unmarshal(responsePayload, &replay); err != nil {
		return Envelope[BillingCheckoutPlan]{}, false, fmt.Errorf("decode billing checkout idempotency response: %w", err)
	}
	replay.IdempotentReplay = true
	return replay, true, nil
}

func insertIdempotentBillingCheckoutPlanResponse(ctx context.Context, tx *sql.Tx, operation, tenantID, projectID, key string, request any, response Envelope[BillingCheckoutPlan]) (Envelope[BillingCheckoutPlan], bool, error) {
	requestFingerprint, err := fingerprint(request)
	if err != nil {
		return Envelope[BillingCheckoutPlan]{}, false, err
	}
	responsePayload, err := jsonBytes(response)
	if err != nil {
		return Envelope[BillingCheckoutPlan]{}, false, fmt.Errorf("marshal billing checkout idempotency response: %w", err)
	}
	result, err := tx.ExecContext(ctx, `
INSERT INTO releasefoundry_idempotency_ledger (operation, tenant_id, project_id, key, request_fingerprint, response_json)
VALUES ($1, $2, $3, $4, $5, $6::jsonb)
ON CONFLICT (operation, tenant_id, project_id, key) DO NOTHING
`, operation, tenantID, projectID, key, requestFingerprint, string(responsePayload))
	if err != nil {
		return Envelope[BillingCheckoutPlan]{}, false, fmt.Errorf("insert billing checkout idempotency ledger: %w", err)
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil || rowsAffected > 0 {
		return Envelope[BillingCheckoutPlan]{}, false, nil
	}
	return loadIdempotentBillingCheckoutPlanReplay(ctx, tx, operation, tenantID, projectID, key, request)
}

func loadIdempotentBillingPortalPlanReplay(ctx context.Context, tx *sql.Tx, operation, tenantID, projectID, key string, request any) (Envelope[BillingPortalPlan], bool, error) {
	var storedFingerprint string
	var responsePayload []byte
	err := tx.QueryRowContext(ctx, `
SELECT request_fingerprint, response_json
FROM releasefoundry_idempotency_ledger
WHERE operation = $1 AND tenant_id = $2 AND project_id = $3 AND key = $4
`, operation, tenantID, projectID, key).Scan(&storedFingerprint, &responsePayload)
	if errors.Is(err, sql.ErrNoRows) {
		return Envelope[BillingPortalPlan]{}, false, nil
	}
	if err != nil {
		return Envelope[BillingPortalPlan]{}, false, fmt.Errorf("load billing portal idempotency ledger: %w", err)
	}
	requestFingerprint, err := fingerprint(request)
	if err != nil {
		return Envelope[BillingPortalPlan]{}, false, err
	}
	if storedFingerprint != requestFingerprint {
		return Envelope[BillingPortalPlan]{}, false, IdempotencyConflictError{Operation: operation, Key: key}
	}
	var replay Envelope[BillingPortalPlan]
	if err := json.Unmarshal(responsePayload, &replay); err != nil {
		return Envelope[BillingPortalPlan]{}, false, fmt.Errorf("decode billing portal idempotency response: %w", err)
	}
	replay.IdempotentReplay = true
	return replay, true, nil
}

func insertIdempotentBillingPortalPlanResponse(ctx context.Context, tx *sql.Tx, operation, tenantID, projectID, key string, request any, response Envelope[BillingPortalPlan]) (Envelope[BillingPortalPlan], bool, error) {
	requestFingerprint, err := fingerprint(request)
	if err != nil {
		return Envelope[BillingPortalPlan]{}, false, err
	}
	responsePayload, err := jsonBytes(response)
	if err != nil {
		return Envelope[BillingPortalPlan]{}, false, fmt.Errorf("marshal billing portal idempotency response: %w", err)
	}
	result, err := tx.ExecContext(ctx, `
INSERT INTO releasefoundry_idempotency_ledger (operation, tenant_id, project_id, key, request_fingerprint, response_json)
VALUES ($1, $2, $3, $4, $5, $6::jsonb)
ON CONFLICT (operation, tenant_id, project_id, key) DO NOTHING
`, operation, tenantID, projectID, key, requestFingerprint, string(responsePayload))
	if err != nil {
		return Envelope[BillingPortalPlan]{}, false, fmt.Errorf("insert billing portal idempotency ledger: %w", err)
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil || rowsAffected > 0 {
		return Envelope[BillingPortalPlan]{}, false, nil
	}
	return loadIdempotentBillingPortalPlanReplay(ctx, tx, operation, tenantID, projectID, key, request)
}

func loadIdempotentBillingWebhookReplay(ctx context.Context, tx *sql.Tx, operation, tenantID, projectID, key string, request any) (Envelope[BillingWebhookIngest], bool, error) {
	var storedFingerprint string
	var responsePayload []byte
	err := tx.QueryRowContext(ctx, `
SELECT request_fingerprint, response_json
FROM releasefoundry_idempotency_ledger
WHERE operation = $1 AND tenant_id = $2 AND project_id = $3 AND key = $4
`, operation, tenantID, projectID, key).Scan(&storedFingerprint, &responsePayload)
	if errors.Is(err, sql.ErrNoRows) {
		return Envelope[BillingWebhookIngest]{}, false, nil
	}
	if err != nil {
		return Envelope[BillingWebhookIngest]{}, false, fmt.Errorf("load billing webhook idempotency ledger: %w", err)
	}
	requestFingerprint, err := fingerprint(request)
	if err != nil {
		return Envelope[BillingWebhookIngest]{}, false, err
	}
	if storedFingerprint != requestFingerprint {
		return Envelope[BillingWebhookIngest]{}, false, IdempotencyConflictError{Operation: operation, Key: key}
	}
	var replay Envelope[BillingWebhookIngest]
	if err := json.Unmarshal(responsePayload, &replay); err != nil {
		return Envelope[BillingWebhookIngest]{}, false, fmt.Errorf("decode billing webhook idempotency response: %w", err)
	}
	replay.IdempotentReplay = true
	return replay, true, nil
}

func insertIdempotentBillingWebhookResponse(ctx context.Context, tx *sql.Tx, operation, tenantID, projectID, key string, request any, response Envelope[BillingWebhookIngest]) (Envelope[BillingWebhookIngest], bool, error) {
	requestFingerprint, err := fingerprint(request)
	if err != nil {
		return Envelope[BillingWebhookIngest]{}, false, err
	}
	responsePayload, err := jsonBytes(response)
	if err != nil {
		return Envelope[BillingWebhookIngest]{}, false, fmt.Errorf("marshal billing webhook idempotency response: %w", err)
	}
	result, err := tx.ExecContext(ctx, `
INSERT INTO releasefoundry_idempotency_ledger (operation, tenant_id, project_id, key, request_fingerprint, response_json)
VALUES ($1, $2, $3, $4, $5, $6::jsonb)
ON CONFLICT (operation, tenant_id, project_id, key) DO NOTHING
`, operation, tenantID, projectID, key, requestFingerprint, string(responsePayload))
	if err != nil {
		return Envelope[BillingWebhookIngest]{}, false, fmt.Errorf("insert billing webhook idempotency ledger: %w", err)
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil || rowsAffected > 0 {
		return Envelope[BillingWebhookIngest]{}, false, nil
	}
	return loadIdempotentBillingWebhookReplay(ctx, tx, operation, tenantID, projectID, key, request)
}

func requireProjectWithDB(ctx context.Context, db *sql.DB, tenantID, projectID string) error {
	var exists bool
	err := db.QueryRowContext(ctx, `SELECT EXISTS(SELECT 1 FROM releasefoundry_projects WHERE tenant_id = $1 AND project_id = $2)`, tenantID, projectID).Scan(&exists)
	if err != nil {
		return fmt.Errorf("load project: %w", err)
	}
	if !exists {
		return NotFoundError{Resource: "project"}
	}
	return nil
}
func requireProject(ctx context.Context, tx *sql.Tx, tenantID, projectID string) error {
	var exists bool
	err := tx.QueryRowContext(ctx, `SELECT EXISTS(SELECT 1 FROM releasefoundry_projects WHERE tenant_id = $1 AND project_id = $2)`, tenantID, projectID).Scan(&exists)
	if err != nil {
		return fmt.Errorf("load project: %w", err)
	}
	if !exists {
		return NotFoundError{Resource: "project"}
	}
	return nil
}

func requireRun(ctx context.Context, tx *sql.Tx, tenantID, projectID, runID string) error {
	var exists bool
	err := tx.QueryRowContext(ctx, `SELECT EXISTS(SELECT 1 FROM releasefoundry_runs WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3)`, tenantID, projectID, runID).Scan(&exists)
	if err != nil {
		return fmt.Errorf("load run: %w", err)
	}
	if !exists {
		return NotFoundError{Resource: "run"}
	}
	return nil
}

func requireRunWithDB(ctx context.Context, db *sql.DB, tenantID, projectID, runID string) error {
	var exists bool
	err := db.QueryRowContext(ctx, `SELECT EXISTS(SELECT 1 FROM releasefoundry_runs WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3)`, tenantID, projectID, runID).Scan(&exists)
	if err != nil {
		return fmt.Errorf("load run: %w", err)
	}
	if !exists {
		return NotFoundError{Resource: "run"}
	}
	return nil
}

func expirePostgresWorkerLeases(ctx context.Context, tx *sql.Tx, tenantID, projectID string, now time.Time) error {
	lastError := WorkerJobError{
		SHA256:             mustFingerprint(JSONMap{"type": "worker_lease_expired", "message": "worker lease expired before completion"}),
		Type:               "worker_lease_expired",
		Message:            "worker lease expired before completion",
		RawPayloadIncluded: false,
		FailedAt:           now,
	}
	lastErrorPayload, err := jsonBytes(lastError)
	if err != nil {
		return fmt.Errorf("marshal expired worker lease error: %w", err)
	}
	rows, err := tx.QueryContext(ctx, `
UPDATE releasefoundry_worker_jobs
SET status = CASE WHEN attempts >= max_attempts THEN $4 ELSE $5 END,
    lease_owner_id = '',
    lease_expires_at = NULL,
    available_at = CASE WHEN attempts >= max_attempts THEN NULL ELSE $3 END,
    last_error = $6::jsonb,
    dead_lettered_at = CASE WHEN attempts >= max_attempts THEN $3 ELSE NULL END,
    updated_at = $3
WHERE tenant_id = $1 AND project_id = $2 AND status = $7 AND lease_expires_at IS NOT NULL AND lease_expires_at <= $3
RETURNING job_id, tenant_id, project_id, job_type, target_id, payload_sha256, status, priority, attempts, max_attempts, lease_owner_id, lease_expires_at, available_at, last_error, result_sha256, idempotency_key, request_id, created_at, updated_at, completed_at, dead_lettered_at
`, tenantID, projectID, now, WorkerJobStatusDeadLettered, WorkerJobStatusRetrying, string(lastErrorPayload), WorkerJobStatusLeased)
	if err != nil {
		return fmt.Errorf("expire worker leases: %w", err)
	}
	defer rows.Close()
	expiredJobs := make([]WorkerJob, 0)
	for rows.Next() {
		job, err := scanPostgresWorkerJob(rows)
		if err != nil {
			return fmt.Errorf("scan expired worker lease: %w", err)
		}
		expiredJobs = append(expiredJobs, job)
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("iterate expired worker leases: %w", err)
	}
	if err := rows.Close(); err != nil {
		return fmt.Errorf("close expired worker leases: %w", err)
	}
	for _, job := range expiredJobs {
		if err := appendPostgresMutationEvidence(ctx, tx, tenantID, projectID, "worker.job.lease_expired", 0, postgresMutationEvidence{
			IdempotencyKey: job.IdempotencyKey,
			RequestID:      job.RequestID,
			RunID:          job.TargetID,
			TargetID:       job.JobID,
			After: JSONMap{
				"job_id":       job.JobID,
				"job_type":     job.JobType,
				"status":       job.Status,
				"attempts":     job.Attempts,
				"max_attempts": job.MaxAttempts,
				"error_sha256": lastError.SHA256,
			},
		}, now); err != nil {
			return err
		}
	}
	return nil
}

func selectPostgresWorkerJobForLease(ctx context.Context, tx *sql.Tx, tenantID, projectID, jobType string, now time.Time) (WorkerJob, error) {
	return scanPostgresWorkerJob(tx.QueryRowContext(ctx, `
SELECT job_id, tenant_id, project_id, job_type, target_id, payload_sha256, status, priority, attempts, max_attempts, lease_owner_id, lease_expires_at, available_at, last_error, result_sha256, idempotency_key, request_id, created_at, updated_at, completed_at, dead_lettered_at
FROM releasefoundry_worker_jobs
WHERE tenant_id = $1
  AND project_id = $2
  AND ($3 = '' OR job_type = $3)
  AND status IN ($4, $5)
  AND (available_at IS NULL OR available_at <= $6)
ORDER BY priority ASC, available_at ASC NULLS FIRST, created_at ASC, job_id ASC
LIMIT 1
FOR UPDATE SKIP LOCKED
`, tenantID, projectID, jobType, WorkerJobStatusQueued, WorkerJobStatusRetrying, now))
}

func loadPostgresWorkerJobForUpdate(ctx context.Context, tx *sql.Tx, tenantID, projectID, jobID string) (WorkerJob, error) {
	job, err := scanPostgresWorkerJob(tx.QueryRowContext(ctx, `
SELECT job_id, tenant_id, project_id, job_type, target_id, payload_sha256, status, priority, attempts, max_attempts, lease_owner_id, lease_expires_at, available_at, last_error, result_sha256, idempotency_key, request_id, created_at, updated_at, completed_at, dead_lettered_at
FROM releasefoundry_worker_jobs
WHERE tenant_id = $1 AND project_id = $2 AND job_id = $3
FOR UPDATE
`, tenantID, projectID, jobID))
	if errors.Is(err, sql.ErrNoRows) {
		return WorkerJob{}, NotFoundError{Resource: "worker job"}
	}
	return job, err
}

func updatePostgresWorkerJobLease(ctx context.Context, tx *sql.Tx, tenantID, projectID, jobID, leaseOwnerID string, leaseExpiresAt, now time.Time) (WorkerJob, error) {
	return scanPostgresWorkerJob(tx.QueryRowContext(ctx, `
UPDATE releasefoundry_worker_jobs
SET status = $4, attempts = attempts + 1, lease_owner_id = $5, lease_expires_at = $6, updated_at = $7
WHERE tenant_id = $1 AND project_id = $2 AND job_id = $3
RETURNING job_id, tenant_id, project_id, job_type, target_id, payload_sha256, status, priority, attempts, max_attempts, lease_owner_id, lease_expires_at, available_at, last_error, result_sha256, idempotency_key, request_id, created_at, updated_at, completed_at, dead_lettered_at
`, tenantID, projectID, jobID, WorkerJobStatusLeased, leaseOwnerID, leaseExpiresAt, now))
}

func updatePostgresWorkerJobHeartbeat(ctx context.Context, tx *sql.Tx, tenantID, projectID, jobID string, leaseExpiresAt, now time.Time) (WorkerJob, error) {
	return scanPostgresWorkerJob(tx.QueryRowContext(ctx, `
UPDATE releasefoundry_worker_jobs
SET lease_expires_at = GREATEST(lease_expires_at, $4), updated_at = $5
WHERE tenant_id = $1 AND project_id = $2 AND job_id = $3
RETURNING job_id, tenant_id, project_id, job_type, target_id, payload_sha256, status, priority, attempts, max_attempts, lease_owner_id, lease_expires_at, available_at, last_error, result_sha256, idempotency_key, request_id, created_at, updated_at, completed_at, dead_lettered_at
`, tenantID, projectID, jobID, leaseExpiresAt, now))
}

func updatePostgresWorkerJobComplete(ctx context.Context, tx *sql.Tx, tenantID, projectID, jobID, resultSHA string, now time.Time) (WorkerJob, error) {
	return scanPostgresWorkerJob(tx.QueryRowContext(ctx, `
UPDATE releasefoundry_worker_jobs
SET status = $4, lease_owner_id = '', lease_expires_at = NULL, result_sha256 = $5, updated_at = $6, completed_at = $6
WHERE tenant_id = $1 AND project_id = $2 AND job_id = $3
RETURNING job_id, tenant_id, project_id, job_type, target_id, payload_sha256, status, priority, attempts, max_attempts, lease_owner_id, lease_expires_at, available_at, last_error, result_sha256, idempotency_key, request_id, created_at, updated_at, completed_at, dead_lettered_at
`, tenantID, projectID, jobID, WorkerJobStatusCompleted, resultSHA, now))
}

func updatePostgresWorkerJobFail(ctx context.Context, tx *sql.Tx, tenantID, projectID, jobID, status string, availableAt, deadLetteredAt *time.Time, lastError WorkerJobError, now time.Time) (WorkerJob, error) {
	lastErrorPayload, err := jsonBytes(lastError)
	if err != nil {
		return WorkerJob{}, fmt.Errorf("marshal worker last error: %w", err)
	}
	return scanPostgresWorkerJob(tx.QueryRowContext(ctx, `
UPDATE releasefoundry_worker_jobs
SET status = $4, lease_owner_id = '', lease_expires_at = NULL, available_at = $5, dead_lettered_at = $6, last_error = $7::jsonb, updated_at = $8
WHERE tenant_id = $1 AND project_id = $2 AND job_id = $3
RETURNING job_id, tenant_id, project_id, job_type, target_id, payload_sha256, status, priority, attempts, max_attempts, lease_owner_id, lease_expires_at, available_at, last_error, result_sha256, idempotency_key, request_id, created_at, updated_at, completed_at, dead_lettered_at
`, tenantID, projectID, jobID, status, availableAt, deadLetteredAt, string(lastErrorPayload), now))
}

type workerJobScanner interface {
	Scan(dest ...any) error
}

func scanPostgresWorkerJob(scanner workerJobScanner) (WorkerJob, error) {
	var job WorkerJob
	var leaseExpiresAt sql.NullTime
	var availableAt sql.NullTime
	var completedAt sql.NullTime
	var deadLetteredAt sql.NullTime
	var lastErrorPayload []byte
	err := scanner.Scan(&job.JobID, &job.TenantID, &job.ProjectID, &job.JobType, &job.TargetID, &job.PayloadSHA256, &job.Status, &job.Priority, &job.Attempts, &job.MaxAttempts, &job.LeaseOwnerID, &leaseExpiresAt, &availableAt, &lastErrorPayload, &job.ResultSHA256, &job.IdempotencyKey, &job.RequestID, &job.CreatedAt, &job.UpdatedAt, &completedAt, &deadLetteredAt)
	if err != nil {
		return WorkerJob{}, err
	}
	job.SchemaVersion = ControlPlaneSchemaVersion
	job.RawPayloadIncluded = false
	if leaseExpiresAt.Valid {
		job.LeaseExpiresAt = &leaseExpiresAt.Time
	}
	if availableAt.Valid {
		job.AvailableAt = &availableAt.Time
	}
	if completedAt.Valid {
		job.CompletedAt = &completedAt.Time
	}
	if deadLetteredAt.Valid {
		job.DeadLetteredAt = &deadLetteredAt.Time
	}
	if len(lastErrorPayload) > 0 {
		var lastError WorkerJobError
		if err := json.Unmarshal(lastErrorPayload, &lastError); err != nil {
			return WorkerJob{}, fmt.Errorf("decode worker last error: %w", err)
		}
		job.LastError = &lastError
	}
	return job, nil
}

func scanPostgresArtifactManifest(scanner workerJobScanner) (ArtifactManifest, error) {
	var manifest ArtifactManifest
	err := scanner.Scan(&manifest.TenantID, &manifest.ProjectID, &manifest.RunID, &manifest.ArtifactID, &manifest.ManifestSHA256, &manifest.APIKeyID, &manifest.RequestID, &manifest.CreatedAt)
	if err != nil {
		return ArtifactManifest{}, err
	}
	manifest.SchemaVersion = ControlPlaneSchemaVersion
	manifest.RawPayloadIncluded = false
	return manifest, nil
}

func (repository *PostgresRepository) postgresRun(ctx context.Context, tenantID, projectID, runID string) (Run, error) {
	var run Run
	var metadataPayload []byte
	err := repository.db.QueryRowContext(ctx, `
SELECT tenant_id, project_id, run_id, dataset_id, agent_ref, status, metadata
FROM releasefoundry_runs
WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3
`, tenantID, projectID, runID).Scan(&run.TenantID, &run.ProjectID, &run.RunID, &run.DatasetID, &run.AgentRef, &run.Status, &metadataPayload)
	if errors.Is(err, sql.ErrNoRows) {
		return Run{}, NotFoundError{Resource: "run"}
	}
	if err != nil {
		return Run{}, fmt.Errorf("load run: %w", err)
	}
	if len(metadataPayload) > 0 {
		if err := json.Unmarshal(metadataPayload, &run.Metadata); err != nil {
			return Run{}, fmt.Errorf("decode run metadata: %w", err)
		}
	}
	return run, nil
}

func (repository *PostgresRepository) postgresRunUploads(ctx context.Context, tenantID, projectID, runID string) ([]RunUpload, error) {
	rows, err := repository.db.QueryContext(ctx, `
SELECT tenant_id, project_id, run_id, upload_id, result_sha256, api_key_id, request_id, created_at
FROM releasefoundry_run_uploads
WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3
ORDER BY created_at ASC, upload_id ASC
`, tenantID, projectID, runID)
	if err != nil {
		return nil, fmt.Errorf("list run uploads: %w", err)
	}
	defer rows.Close()
	uploads := []RunUpload{}
	for rows.Next() {
		var upload RunUpload
		if err := rows.Scan(&upload.TenantID, &upload.ProjectID, &upload.RunID, &upload.UploadID, &upload.ResultSHA256, &upload.APIKeyID, &upload.RequestID, &upload.CreatedAt); err != nil {
			return nil, fmt.Errorf("scan run upload: %w", err)
		}
		upload.SchemaVersion = ControlPlaneSchemaVersion
		upload.RawPayloadIncluded = false
		uploads = append(uploads, upload)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate run uploads: %w", err)
	}
	return uploads, nil
}

func (repository *PostgresRepository) postgresTraceBatches(ctx context.Context, tenantID, projectID, runID string) ([]TraceBatch, error) {
	rows, err := repository.db.QueryContext(ctx, `
SELECT tenant_id, project_id, run_id, batch_id, observation_count, observations_sha256, api_key_id, request_id, created_at
FROM releasefoundry_trace_batches
WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3
ORDER BY created_at ASC, batch_id ASC
`, tenantID, projectID, runID)
	if err != nil {
		return nil, fmt.Errorf("list trace batches: %w", err)
	}
	defer rows.Close()
	batches := []TraceBatch{}
	for rows.Next() {
		var batch TraceBatch
		if err := rows.Scan(&batch.TenantID, &batch.ProjectID, &batch.RunID, &batch.BatchID, &batch.ObservationCount, &batch.ObservationsSHA256, &batch.APIKeyID, &batch.RequestID, &batch.CreatedAt); err != nil {
			return nil, fmt.Errorf("scan trace batch: %w", err)
		}
		batch.SchemaVersion = ControlPlaneSchemaVersion
		batch.RawPayloadIncluded = false
		batches = append(batches, batch)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate trace batches: %w", err)
	}
	return batches, nil
}

func (repository *PostgresRepository) postgresArtifactManifests(ctx context.Context, tenantID, projectID, runID string) ([]ArtifactManifest, error) {
	if err := requireRunWithDB(ctx, repository.db, tenantID, projectID, runID); err != nil {
		return nil, err
	}
	rows, err := repository.db.QueryContext(ctx, `
SELECT tenant_id, project_id, run_id, artifact_id, manifest_sha256, api_key_id, request_id, created_at
FROM releasefoundry_artifact_manifests
WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3
ORDER BY created_at ASC, artifact_id ASC
`, tenantID, projectID, runID)
	if err != nil {
		return nil, fmt.Errorf("list artifact manifests: %w", err)
	}
	defer rows.Close()
	manifests := []ArtifactManifest{}
	for rows.Next() {
		manifest, err := scanPostgresArtifactManifest(rows)
		if err != nil {
			return nil, err
		}
		manifests = append(manifests, manifest)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate artifact manifests: %w", err)
	}
	return manifests, nil
}

type auditEventScanner interface {
	Scan(dest ...any) error
}

type auditEventRows interface {
	auditEventScanner
	Next() bool
	Err() error
}

func scanPostgresAuditEvent(scanner auditEventScanner) (AuditEvent, error) {
	event := AuditEvent{}
	var afterPayload []byte
	err := scanner.Scan(&event.TenantID, &event.ProjectID, &event.AuditEventID, &event.Action, &event.TargetID, &event.APIKeyID, &event.IdempotencyKey, &event.RequestID, &event.PreviousHash, &event.EventHash, &afterPayload, &event.CreatedAt)
	if err != nil {
		return AuditEvent{}, err
	}
	if len(afterPayload) == 0 {
		event.After = JSONMap{}
	} else if err := json.Unmarshal(afterPayload, &event.After); err != nil {
		return AuditEvent{}, fmt.Errorf("unmarshal audit event after_json: %w", err)
	}
	event.SchemaVersion = ControlPlaneSchemaVersion
	event.CreatedAt = event.CreatedAt.UTC()
	event.CreatedAtUnixNS = event.CreatedAt.UnixNano()
	return event, nil
}

func verifyPostgresAuditChainRows(rows auditEventRows, tenantID, projectID string, checkedAt time.Time) (AuditChainVerification, error) {
	result := AuditChainVerification{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, Verified: true, CheckedAt: checkedAt}
	previousHash := ""
	for rows.Next() {
		event, err := scanPostgresAuditEvent(rows)
		if err != nil {
			return AuditChainVerification{}, err
		}
		if result.EventCount == 0 {
			result.HeadHash = event.EventHash
		}
		result.EventCount++
		if event.PreviousHash != previousHash {
			return invalidAuditChain(result, event, fmt.Sprintf("previous_hash mismatch: got %q want %q", event.PreviousHash, previousHash)), nil
		}
		expectedHash, err := postgresAuditEventHash(event)
		if err != nil {
			return AuditChainVerification{}, err
		}
		if event.EventHash != expectedHash {
			return invalidAuditChain(result, event, fmt.Sprintf("event_hash mismatch: got %q want %q", event.EventHash, expectedHash)), nil
		}
		previousHash = event.EventHash
		result.TailHash = previousHash
	}
	if err := rows.Err(); err != nil {
		return AuditChainVerification{}, err
	}
	return result, nil
}

func invalidAuditChain(result AuditChainVerification, event AuditEvent, reason string) AuditChainVerification {
	result.Verified = false
	result.FirstInvalidEvent = &event
	result.FirstInvalidReason = reason
	return result
}

func postgresAuditEventHash(event AuditEvent) (string, error) {
	return fingerprint(JSONMap{
		"tenant_id":         event.TenantID,
		"project_id":        event.ProjectID,
		"audit_event_id":    event.AuditEventID,
		"action":            event.Action,
		"target_id":         event.TargetID,
		"api_key_id":        event.APIKeyID,
		"idempotency_key":   event.IdempotencyKey,
		"request_id":        event.RequestID,
		"previous_hash":     event.PreviousHash,
		"after":             defaultMap(event.After),
		"created_at_unixns": event.CreatedAt.UnixNano(),
	})
}

type postgresMutationEvidence struct {
	APIKeyID       string
	IdempotencyKey string
	RequestID      string
	RunID          string
	TargetID       string
	After          JSONMap
}

func appendPostgresUsageEvent(ctx context.Context, tx *sql.Tx, tenantID, projectID, operation string, units int, evidence postgresMutationEvidence, now time.Time) error {
	if units < 1 {
		units = 1
	}
	if gated, err := appendSaaSQuotaUsageIfAvailable(ctx, tx, tenantID, projectID, operation, units, evidence, now); gated || err != nil {
		return err
	}
	if err := checkLocalPostgresUsageQuota(ctx, tx, tenantID, projectID, operation, units); err != nil {
		return err
	}
	if err := consumeLocalPostgresAPIKeyRateLimit(ctx, tx, tenantID, projectID, evidence.APIKeyID, operation, units, now); err != nil {
		return err
	}
	usageEventID := stablePostgresTimedID("usage", operation, now)
	_, err := tx.ExecContext(ctx, `
INSERT INTO releasefoundry_quota_ledger (tenant_id, project_id, usage_event_id, operation, units, api_key_id, idempotency_key, request_id, run_id, target_id, created_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
`, tenantID, projectID, usageEventID, operation, units, evidence.APIKeyID, evidence.IdempotencyKey, evidence.RequestID, evidence.RunID, evidence.TargetID, now)
	if err != nil {
		return fmt.Errorf("append usage ledger: %w", err)
	}
	return nil
}

func appendSaaSQuotaUsageIfAvailable(ctx context.Context, tx *sql.Tx, tenantID, projectID, operation string, units int, evidence postgresMutationEvidence, now time.Time) (bool, error) {
	if !looksLikeUUID(tenantID) || !looksLikeUUID(projectID) {
		return false, nil
	}
	available, err := postgresFunctionExists(ctx, tx, "check_quota_and_insert_usage", 12)
	if err != nil {
		return false, err
	}
	if !available {
		return false, nil
	}
	metadata := JSONMap{
		"api_key_id":      evidence.APIKeyID,
		"idempotency_key": evidence.IdempotencyKey,
		"request_id":      evidence.RequestID,
		"run_id":          evidence.RunID,
		"target_id":       evidence.TargetID,
	}
	if len(evidence.After) > 0 {
		metadata["after"] = evidence.After
	}
	metadataJSON, err := jsonBytes(RedactSensitive(metadata))
	if err != nil {
		return true, fmt.Errorf("marshal SaaS quota metadata: %w", err)
	}
	var idempotencyKeyID any
	if strings.TrimSpace(evidence.IdempotencyKey) != "" {
		var keyID string
		err := tx.QueryRowContext(ctx, `
SELECT id
FROM idempotency_keys
WHERE organization_id = $1::uuid AND project_id IS NOT DISTINCT FROM $2::uuid AND idempotency_key = $3
LIMIT 1
`, tenantID, projectID, evidence.IdempotencyKey).Scan(&keyID)
		if err != nil && !errors.Is(err, sql.ErrNoRows) {
			return true, fmt.Errorf("load SaaS idempotency key: %w", err)
		}
		if keyID != "" {
			idempotencyKeyID = keyID
		}
	}
	var allowed bool
	var idempotentReplay bool
	var returnedOperation string
	var meter string
	var quantityFloat float64
	var deniedPolicyID sql.NullString
	var denialReason sql.NullString
	var usageLedgerID sql.NullString
	err = tx.QueryRowContext(ctx, `
SELECT allowed, usage_ledger_id::text, idempotent_replay, operation, meter, quantity::float8, denied_policy_id::text, denial_reason
FROM check_quota_and_insert_usage($1::uuid, $2::uuid, $3, $4, NULL, NULL, $5::uuid, 'go-postgres', $6, $7, $8::jsonb, NULL)
`, tenantID, projectID, operation, units, idempotencyKeyID, evidence.TargetID, now, string(metadataJSON)).Scan(&allowed, &usageLedgerID, &idempotentReplay, &returnedOperation, &meter, &quantityFloat, &deniedPolicyID, &denialReason)
	if err != nil {
		return true, fmt.Errorf("append SaaS quota usage: %w", err)
	}
	if !allowed {
		used, limit := saasQuotaDenialContext(ctx, tx, tenantID, projectID, meter, deniedPolicyID.String, now)
		return true, QuotaExceededError{Operation: returnedOperation, Limit: limit, Used: used, Requested: int(quantityFloat)}
	}
	return true, nil
}

func checkLocalPostgresUsageQuota(ctx context.Context, tx *sql.Tx, tenantID, projectID, operation string, units int) error {
	var limit int
	err := tx.QueryRowContext(ctx, `
SELECT limit_units
FROM releasefoundry_usage_quota_policies
WHERE tenant_id = $1 AND project_id = $2 AND operation = $3 AND status = 'active'
LIMIT 1
`, tenantID, projectID, operation).Scan(&limit)
	if errors.Is(err, sql.ErrNoRows) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("load usage quota policy: %w", err)
	}
	var used int
	if err := tx.QueryRowContext(ctx, `
SELECT COALESCE(SUM(units), 0)::int
FROM releasefoundry_quota_ledger
WHERE tenant_id = $1 AND project_id = $2 AND operation = $3
`, tenantID, projectID, operation).Scan(&used); err != nil {
		return fmt.Errorf("load usage quota total: %w", err)
	}
	if used+units > limit {
		return QuotaExceededError{Operation: operation, Limit: limit, Used: used, Requested: units}
	}
	return nil
}

func configureSaaSUsageQuotaPolicy(ctx context.Context, tx *sql.Tx, tenantID, projectID string, meter OperationMeter, limit int, now time.Time) (bool, error) {
	if !looksLikeUUID(tenantID) || !looksLikeUUID(projectID) {
		return false, nil
	}
	available, err := postgresTableExists(ctx, tx, "quota_policies")
	if err != nil || !available {
		return available, err
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO quota_policies (organization_id, project_id, meter, period, limit_quantity, enforcement_mode, status, effective_from, metadata)
VALUES ($1::uuid, $2::uuid, $3, 'day', $4, 'hard', 'active', $5, $6::jsonb)
ON CONFLICT (organization_id, project_id, meter, period)
DO UPDATE SET limit_quantity = EXCLUDED.limit_quantity, enforcement_mode = EXCLUDED.enforcement_mode, status = EXCLUDED.status, effective_from = EXCLUDED.effective_from, metadata = EXCLUDED.metadata
`, tenantID, projectID, meter.Meter, limit, now, `{"configured_by":"go-postgres-repository"}`)
	if err != nil {
		return true, fmt.Errorf("configure SaaS usage quota policy: %w", err)
	}
	return true, nil
}

func (repository *PostgresRepository) usageOperationTotal(tenantID, projectID, operation string) (int, int, error) {
	ctx := context.Background()
	var used int
	var events int
	err := repository.db.QueryRowContext(ctx, `
SELECT COALESCE(SUM(units), 0)::int, COUNT(*)::int
FROM releasefoundry_quota_ledger
WHERE tenant_id = $1 AND project_id = $2 AND operation = $3
`, tenantID, projectID, operation).Scan(&used, &events)
	if err != nil {
		return 0, 0, fmt.Errorf("load usage operation total: %w", err)
	}
	return used, events, nil
}

func postgresTableExists(ctx context.Context, tx *sql.Tx, table string) (bool, error) {
	var exists bool
	err := tx.QueryRowContext(ctx, `SELECT to_regclass($1) IS NOT NULL`, table).Scan(&exists)
	if err != nil {
		return false, fmt.Errorf("check postgres table %s: %w", table, err)
	}
	return exists, nil
}

func postgresFunctionExists(ctx context.Context, tx *sql.Tx, name string, argCount int) (bool, error) {
	var exists bool
	err := tx.QueryRowContext(ctx, `
SELECT EXISTS (
  SELECT 1
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = current_schema()
    AND p.proname = $1
    AND p.pronargs = $2
)
`, name, argCount).Scan(&exists)
	if err != nil {
		return false, fmt.Errorf("check postgres function %s: %w", name, err)
	}
	return exists, nil
}

func looksLikeUUID(value string) bool {
	value = strings.TrimSpace(value)
	if len(value) != 36 {
		return false
	}
	for index, char := range value {
		switch index {
		case 8, 13, 18, 23:
			if char != '-' {
				return false
			}
		default:
			if !((char >= '0' && char <= '9') || (char >= 'a' && char <= 'f') || (char >= 'A' && char <= 'F')) {
				return false
			}
		}
	}
	return true
}

func postgresRelationMissing(err error) bool {
	var pqErr *pq.Error
	if errors.As(err, &pqErr) {
		return string(pqErr.Code) == "42P01"
	}
	return false
}

func saasQuotaDenialContext(ctx context.Context, tx *sql.Tx, tenantID, projectID, meter, policyID string, at time.Time) (int, int) {
	limit := 0
	if policyID != "" {
		_ = tx.QueryRowContext(ctx, `SELECT limit_quantity::int FROM quota_policies WHERE id = $1::uuid`, policyID).Scan(&limit)
	}
	var used int
	_ = tx.QueryRowContext(ctx, `
SELECT COALESCE(SUM(quantity), 0)::int
FROM usage_ledger
WHERE organization_id = $1::uuid AND project_id IS NOT DISTINCT FROM $2::uuid AND meter = $3 AND period_start <= $4 AND period_end > $4
`, tenantID, projectID, meter, at).Scan(&used)
	return used, limit
}

func appendPostgresAuditEvent(ctx context.Context, tx *sql.Tx, tenantID, projectID, action string, evidence postgresMutationEvidence, now time.Time) error {
	now = now.UTC().Truncate(time.Microsecond)
	var previousHash string
	err := tx.QueryRowContext(ctx, `
SELECT event_hash
FROM releasefoundry_audit_events
WHERE tenant_id = $1 AND project_id = $2
ORDER BY created_at DESC, audit_event_id DESC
LIMIT 1
`, tenantID, projectID).Scan(&previousHash)
	if errors.Is(err, sql.ErrNoRows) {
		previousHash = ""
	} else if err != nil {
		return fmt.Errorf("load audit tail: %w", err)
	}
	after := defaultMap(evidence.After)
	afterPayload, err := jsonBytes(after)
	if err != nil {
		return fmt.Errorf("marshal audit after: %w", err)
	}
	auditEventID, err := postgresAuditEventID(action, evidence, after, now)
	if err != nil {
		return err
	}
	eventHash, err := fingerprint(JSONMap{
		"tenant_id":         tenantID,
		"project_id":        projectID,
		"audit_event_id":    auditEventID,
		"action":            action,
		"target_id":         evidence.TargetID,
		"api_key_id":        evidence.APIKeyID,
		"idempotency_key":   evidence.IdempotencyKey,
		"request_id":        evidence.RequestID,
		"previous_hash":     previousHash,
		"after":             after,
		"created_at_unixns": now.UnixNano(),
	})
	if err != nil {
		return err
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO releasefoundry_audit_events (tenant_id, project_id, audit_event_id, action, target_id, api_key_id, idempotency_key, request_id, previous_hash, event_hash, after_json, created_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12)
`, tenantID, projectID, auditEventID, action, evidence.TargetID, evidence.APIKeyID, evidence.IdempotencyKey, evidence.RequestID, previousHash, eventHash, string(afterPayload), now)
	if err != nil {
		return fmt.Errorf("append audit log: %w", err)
	}
	return nil
}

func appendPostgresMutationEvidence(ctx context.Context, tx *sql.Tx, tenantID, projectID, operation string, units int, evidence postgresMutationEvidence, now time.Time) error {
	if units > 0 {
		if err := appendPostgresUsageEvent(ctx, tx, tenantID, projectID, operation, units, evidence, now); err != nil {
			return err
		}
	}
	if err := appendPostgresAuditEvent(ctx, tx, tenantID, projectID, operation, evidence, now); err != nil {
		return err
	}
	return nil
}

func requirePostgresWorkerJobLease(job WorkerJob, leaseOwnerID string, now time.Time) error {
	if strings.TrimSpace(leaseOwnerID) == "" {
		return fmt.Errorf("lease_owner_id is required")
	}
	if job.Status != WorkerJobStatusLeased || job.LeaseOwnerID != leaseOwnerID || job.LeaseExpiresAt == nil || !job.LeaseExpiresAt.After(now) {
		return fmt.Errorf("worker job is not leased by %s", leaseOwnerID)
	}
	return nil
}

func rollbackUnlessCommitted(tx *sql.Tx) {
	if tx != nil {
		_ = tx.Rollback()
	}
}

func jsonBytes(value any) ([]byte, error) {
	return json.Marshal(normalizeJSON(value))
}

func defaultMap(value JSONMap) JSONMap {
	if value == nil {
		return JSONMap{}
	}
	return value
}

func defaultCases(value []DatasetCase) []DatasetCase {
	if value == nil {
		return []DatasetCase{}
	}
	return value
}

func stablePostgresID(prefix, name string) string {
	stem := strings.Trim(strings.ToLower(name), " _-")
	stem = strings.ReplaceAll(stem, " ", "_")
	if stem == "" {
		stem = "local"
	}
	return prefix + "_" + stem
}

func stablePostgresWorkerJobID(jobType string, now time.Time) string {
	return fmt.Sprintf("%s_%d", stablePostgresID("job", jobType), now.UnixNano())
}

func stablePostgresTimedID(prefix, name string, now time.Time) string {
	return fmt.Sprintf("%s_%d", stablePostgresID(prefix, name), now.UnixNano())
}

func postgresAuditEventID(action string, evidence postgresMutationEvidence, after JSONMap, now time.Time) (string, error) {
	evidenceHash, err := fingerprint(JSONMap{
		"target_id":       evidence.TargetID,
		"api_key_id":      evidence.APIKeyID,
		"idempotency_key": evidence.IdempotencyKey,
		"request_id":      evidence.RequestID,
		"run_id":          evidence.RunID,
		"after":           after,
	})
	if err != nil {
		return "", fmt.Errorf("fingerprint audit evidence: %w", err)
	}
	return stablePostgresTimedID("audit", action+"_"+evidenceHash[:16], now), nil
}
