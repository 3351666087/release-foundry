package ashrclone

import (
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"time"

	_ "github.com/lib/pq"
)

var ErrPostgresRepositoryNotImplemented = errors.New("postgres repository is not implemented yet")

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
	return Envelope[BootstrapResult]{}, repository.notImplemented("bootstrap_project")
}

func (repository *PostgresRepository) SubmitRun(tenantID, projectID, datasetID, agentRef, runID string, metadata JSONMap, options IdempotencyOptions) (Envelope[Run], error) {
	return Envelope[Run]{}, repository.notImplemented("sdk_submit")
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
