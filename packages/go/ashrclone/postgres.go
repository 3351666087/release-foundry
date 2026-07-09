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
	return Envelope[RunUpload]{}, repository.notImplemented("run.upload")
}

func (repository *PostgresRepository) IngestTrace(tenantID, projectID, runID string, observations []JSONMap, options IngestTraceOptions) (Envelope[TraceBatch], error) {
	return Envelope[TraceBatch]{}, repository.notImplemented("trace.ingest")
}

func (repository *PostgresRepository) CreateArtifactManifest(tenantID, projectID, runID string, manifest JSONMap, options ArtifactManifestOptions) (Envelope[ArtifactManifest], error) {
	return Envelope[ArtifactManifest]{}, repository.notImplemented("artifact.manifest.create")
}

func (repository *PostgresRepository) ListArtifactManifests(tenantID, projectID, runID string) (Envelope[ArtifactManifestList], error) {
	return Envelope[ArtifactManifestList]{}, repository.notImplemented("artifact.manifest.list")
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
	if err := tx.Commit(); err != nil {
		return Envelope[WorkerJob]{}, fmt.Errorf("%s commit: %w", operation, err)
	}
	return Envelope[WorkerJob]{Operation: operation, Status: "ok", Result: job}, nil
}

func (repository *PostgresRepository) notImplemented(operation string) error {
	return fmt.Errorf("%s: %w", operation, ErrPostgresRepositoryNotImplemented)
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
