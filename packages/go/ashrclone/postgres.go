package ashrclone

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	_ "github.com/lib/pq"
)

var ErrPostgresRepositoryNotImplemented = errors.New("postgres repository is not implemented yet")

const PostgresSchemaSQL = `
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
INSERT INTO ashr_worker_jobs (tenant_id, project_id, job_id, job_type, target_id, payload_sha256, status, priority, attempts, max_attempts, available_at, idempotency_key, request_id, created_at, updated_at)
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
FROM ashr_worker_jobs
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
INSERT INTO ashr_run_uploads (tenant_id, project_id, run_id, upload_id, result_sha256, api_key_id, request_id, idempotency_key, created_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
`, tenantID, projectID, runID, uploadID, resultSHA, options.APIKeyID, options.RequestID, options.IdempotencyKey, now)
	if err != nil {
		return Envelope[RunUpload]{}, fmt.Errorf("insert run upload: %w", err)
	}
	_, err = tx.ExecContext(ctx, `
UPDATE ashr_runs SET status = 'uploaded', updated_at = $4
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
INSERT INTO ashr_trace_batches (tenant_id, project_id, run_id, batch_id, observation_count, observations_sha256, api_key_id, request_id, idempotency_key, created_at)
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
INSERT INTO ashr_artifact_manifests (tenant_id, project_id, run_id, artifact_id, manifest_sha256, api_key_id, request_id, idempotency_key, created_at)
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
	if err := requireRunWithDB(ctx, repository.db, tenantID, projectID, runID); err != nil {
		return Envelope[ArtifactManifestList]{}, err
	}
	rows, err := repository.db.QueryContext(ctx, `
SELECT tenant_id, project_id, run_id, artifact_id, manifest_sha256, api_key_id, request_id, created_at
FROM ashr_artifact_manifests
WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3
ORDER BY created_at ASC, artifact_id ASC
`, tenantID, projectID, runID)
	if err != nil {
		return Envelope[ArtifactManifestList]{}, fmt.Errorf("list artifact manifests: %w", err)
	}
	defer rows.Close()
	manifests := []ArtifactManifest{}
	for rows.Next() {
		manifest, err := scanPostgresArtifactManifest(rows)
		if err != nil {
			return Envelope[ArtifactManifestList]{}, err
		}
		manifests = append(manifests, manifest)
	}
	if err := rows.Err(); err != nil {
		return Envelope[ArtifactManifestList]{}, fmt.Errorf("iterate artifact manifests: %w", err)
	}
	result := ArtifactManifestList{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, RunID: runID, Manifests: manifests, Count: len(manifests)}
	return Envelope[ArtifactManifestList]{Operation: "artifact_manifests", Status: "ok", Result: result}, nil
}

func (repository *PostgresRepository) VerifyAuditChain(tenantID, projectID string) (Envelope[AuditChainVerification], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[AuditChainVerification]{}, err
	}
	ctx := context.Background()
	rows, err := repository.db.QueryContext(ctx, `
SELECT tenant_id, project_id, audit_event_id, action, target_id, api_key_id, idempotency_key, request_id, previous_hash, event_hash, after_json, created_at
FROM ashr_audit_events
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

func (repository *PostgresRepository) UsageSnapshot(tenantID, projectID string) (Envelope[UsageSnapshot], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[UsageSnapshot]{}, err
	}
	ctx := context.Background()
	rows, err := repository.db.QueryContext(ctx, `
SELECT operation, COALESCE(SUM(units), 0)::int, COUNT(*)::int
FROM ashr_quota_ledger
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
	return Envelope[APIKeyCreateResult]{}, repository.notImplemented("create_api_key")
}

func (repository *PostgresRepository) ListAPIKeys(tenantID, projectID string) (Envelope[APIKeyListResult], error) {
	return Envelope[APIKeyListResult]{}, repository.notImplemented("list_api_keys")
}

func (repository *PostgresRepository) RevokeAPIKey(tenantID, projectID, keyID string) (Envelope[APIKeyRecord], error) {
	return Envelope[APIKeyRecord]{}, repository.notImplemented("revoke_api_key")
}

func (repository *PostgresRepository) VerifyAPIKeySecret(tenantID, projectID, keyID, secret, scope string) (Envelope[APIKeyVerifyResult], error) {
	return Envelope[APIKeyVerifyResult]{}, repository.notImplemented("verify_api_key_secret")
}

func (repository *PostgresRepository) ConfigureAPIKeyRateLimit(tenantID, projectID, keyID, operation string, limit int) (Envelope[APIKeyRateLimit], error) {
	return Envelope[APIKeyRateLimit]{}, repository.notImplemented("configure_api_key_rate_limit")
}

func (repository *PostgresRepository) APIKeyRateLimitSnapshot(tenantID, projectID, keyID string) (Envelope[APIKeyRateLimitSnapshot], error) {
	return Envelope[APIKeyRateLimitSnapshot]{}, repository.notImplemented("api_key_rate_limit_snapshot")
}

func (repository *PostgresRepository) PreflightAPIKey(options PreflightOptions) (Envelope[AuthPreflight], error) {
	return Envelope[AuthPreflight]{}, repository.notImplemented("auth.preflight")
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
INSERT INTO ashr_tenants (tenant_id, name, metadata)
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
INSERT INTO ashr_projects (tenant_id, project_id, name, metadata)
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
INSERT INTO ashr_datasets (tenant_id, project_id, dataset_id, name, cases, metadata)
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
INSERT INTO ashr_runs (tenant_id, project_id, run_id, dataset_id, agent_ref, status, metadata)
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
FROM ashr_idempotency_ledger
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
INSERT INTO ashr_idempotency_ledger (operation, tenant_id, project_id, key, request_fingerprint, response_json)
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
FROM ashr_idempotency_ledger
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
INSERT INTO ashr_idempotency_ledger (operation, tenant_id, project_id, key, request_fingerprint, response_json)
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
FROM ashr_idempotency_ledger
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
INSERT INTO ashr_idempotency_ledger (operation, tenant_id, project_id, key, request_fingerprint, response_json)
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
FROM ashr_idempotency_ledger
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
INSERT INTO ashr_idempotency_ledger (operation, tenant_id, project_id, key, request_fingerprint, response_json)
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
FROM ashr_idempotency_ledger
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
INSERT INTO ashr_idempotency_ledger (operation, tenant_id, project_id, key, request_fingerprint, response_json)
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

func requireProject(ctx context.Context, tx *sql.Tx, tenantID, projectID string) error {
	var exists bool
	err := tx.QueryRowContext(ctx, `SELECT EXISTS(SELECT 1 FROM ashr_projects WHERE tenant_id = $1 AND project_id = $2)`, tenantID, projectID).Scan(&exists)
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
	err := tx.QueryRowContext(ctx, `SELECT EXISTS(SELECT 1 FROM ashr_runs WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3)`, tenantID, projectID, runID).Scan(&exists)
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
	err := db.QueryRowContext(ctx, `SELECT EXISTS(SELECT 1 FROM ashr_runs WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3)`, tenantID, projectID, runID).Scan(&exists)
	if err != nil {
		return fmt.Errorf("load run: %w", err)
	}
	if !exists {
		return NotFoundError{Resource: "run"}
	}
	return nil
}

func expirePostgresWorkerLeases(ctx context.Context, tx *sql.Tx, tenantID, projectID string, now time.Time) error {
	_, err := tx.ExecContext(ctx, `
UPDATE ashr_worker_jobs
SET status = $4, lease_owner_id = '', lease_expires_at = NULL, available_at = $3, updated_at = $3
WHERE tenant_id = $1 AND project_id = $2 AND status = $5 AND lease_expires_at IS NOT NULL AND lease_expires_at <= $3
`, tenantID, projectID, now, WorkerJobStatusRetrying, WorkerJobStatusLeased)
	if err != nil {
		return fmt.Errorf("expire worker leases: %w", err)
	}
	return nil
}

func selectPostgresWorkerJobForLease(ctx context.Context, tx *sql.Tx, tenantID, projectID, jobType string, now time.Time) (WorkerJob, error) {
	return scanPostgresWorkerJob(tx.QueryRowContext(ctx, `
SELECT job_id, tenant_id, project_id, job_type, target_id, payload_sha256, status, priority, attempts, max_attempts, lease_owner_id, lease_expires_at, available_at, last_error, result_sha256, idempotency_key, request_id, created_at, updated_at, completed_at, dead_lettered_at
FROM ashr_worker_jobs
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
FROM ashr_worker_jobs
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
UPDATE ashr_worker_jobs
SET status = $4, attempts = attempts + 1, lease_owner_id = $5, lease_expires_at = $6, updated_at = $7
WHERE tenant_id = $1 AND project_id = $2 AND job_id = $3
RETURNING job_id, tenant_id, project_id, job_type, target_id, payload_sha256, status, priority, attempts, max_attempts, lease_owner_id, lease_expires_at, available_at, last_error, result_sha256, idempotency_key, request_id, created_at, updated_at, completed_at, dead_lettered_at
`, tenantID, projectID, jobID, WorkerJobStatusLeased, leaseOwnerID, leaseExpiresAt, now))
}

func updatePostgresWorkerJobHeartbeat(ctx context.Context, tx *sql.Tx, tenantID, projectID, jobID string, leaseExpiresAt, now time.Time) (WorkerJob, error) {
	return scanPostgresWorkerJob(tx.QueryRowContext(ctx, `
UPDATE ashr_worker_jobs
SET lease_expires_at = $4, updated_at = $5
WHERE tenant_id = $1 AND project_id = $2 AND job_id = $3
RETURNING job_id, tenant_id, project_id, job_type, target_id, payload_sha256, status, priority, attempts, max_attempts, lease_owner_id, lease_expires_at, available_at, last_error, result_sha256, idempotency_key, request_id, created_at, updated_at, completed_at, dead_lettered_at
`, tenantID, projectID, jobID, leaseExpiresAt, now))
}

func updatePostgresWorkerJobComplete(ctx context.Context, tx *sql.Tx, tenantID, projectID, jobID, resultSHA string, now time.Time) (WorkerJob, error) {
	return scanPostgresWorkerJob(tx.QueryRowContext(ctx, `
UPDATE ashr_worker_jobs
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
UPDATE ashr_worker_jobs
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
	usageEventID := stablePostgresTimedID("usage", operation, now)
	_, err := tx.ExecContext(ctx, `
INSERT INTO ashr_quota_ledger (tenant_id, project_id, usage_event_id, operation, units, api_key_id, idempotency_key, request_id, run_id, target_id, created_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
`, tenantID, projectID, usageEventID, operation, units, evidence.APIKeyID, evidence.IdempotencyKey, evidence.RequestID, evidence.RunID, evidence.TargetID, now)
	if err != nil {
		return fmt.Errorf("append usage ledger: %w", err)
	}
	return nil
}

func appendPostgresAuditEvent(ctx context.Context, tx *sql.Tx, tenantID, projectID, action string, evidence postgresMutationEvidence, now time.Time) error {
	now = now.UTC().Truncate(time.Microsecond)
	var previousHash string
	err := tx.QueryRowContext(ctx, `
SELECT event_hash
FROM ashr_audit_events
WHERE tenant_id = $1 AND project_id = $2
ORDER BY created_at DESC, audit_event_id DESC
LIMIT 1
`, tenantID, projectID).Scan(&previousHash)
	if errors.Is(err, sql.ErrNoRows) {
		previousHash = ""
	} else if err != nil {
		return fmt.Errorf("load audit tail: %w", err)
	}
	auditEventID := stablePostgresTimedID("audit", action, now)
	after := defaultMap(evidence.After)
	afterPayload, err := jsonBytes(after)
	if err != nil {
		return fmt.Errorf("marshal audit after: %w", err)
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
INSERT INTO ashr_audit_events (tenant_id, project_id, audit_event_id, action, target_id, api_key_id, idempotency_key, request_id, previous_hash, event_hash, after_json, created_at)
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
