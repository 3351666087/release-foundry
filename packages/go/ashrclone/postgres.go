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
	return Envelope[WorkerJob]{}, repository.notImplemented("worker.job.enqueue")
}

func (repository *PostgresRepository) LeaseWorkerJob(tenantID, projectID, leaseOwnerID string, options LeaseWorkerJobOptions) (Envelope[WorkerLeaseResult], error) {
	return Envelope[WorkerLeaseResult]{}, repository.notImplemented("worker.job.lease")
}

func (repository *PostgresRepository) HeartbeatWorkerJob(tenantID, projectID, jobID, leaseOwnerID string, leaseSeconds int) (Envelope[WorkerJob], error) {
	return Envelope[WorkerJob]{}, repository.notImplemented("worker.job.heartbeat")
}

func (repository *PostgresRepository) CompleteWorkerJob(tenantID, projectID, jobID, leaseOwnerID string, result JSONMap, options CompleteWorkerJobOptions) (Envelope[WorkerJob], error) {
	return Envelope[WorkerJob]{}, repository.notImplemented("worker.job.complete")
}

func (repository *PostgresRepository) FailWorkerJob(tenantID, projectID, jobID, leaseOwnerID string, failure JSONMap, options FailWorkerJobOptions) (Envelope[WorkerJob], error) {
	return Envelope[WorkerJob]{}, repository.notImplemented("worker.job.fail")
}

func (repository *PostgresRepository) ListWorkerJobs(tenantID, projectID string, options ListWorkerJobsOptions) (Envelope[WorkerJobList], error) {
	return Envelope[WorkerJobList]{}, repository.notImplemented("worker.job.list")
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
