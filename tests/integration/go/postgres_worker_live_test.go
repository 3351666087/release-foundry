package gointegration

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"testing"
	"time"

	ashrclone "github.com/ashr-labs/ashr/packages/go/ashrclone"
	_ "github.com/lib/pq"
)

func TestPostgresWorkerDurabilityLiveOptIn(t *testing.T) {
	dsn := os.Getenv("A1_POSTGRES_TEST_DSN")
	if dsn == "" {
		t.Skip("set A1_POSTGRES_TEST_DSN to run live Postgres worker durability proof")
	}
	repository, err := ashrclone.OpenPostgresRepository(dsn)
	if err != nil {
		t.Fatalf("open postgres repository: %v", err)
	}
	if err := repository.Migrate(context.Background()); err != nil {
		t.Fatalf("migrate postgres repository: %v", err)
	}

	suffix := fmt.Sprintf("%d", time.Now().UTC().UnixNano())
	tenantID := "tenant_worker_live_" + suffix
	projectID := "project_worker_live_" + suffix
	boot, err := repository.BootstrapProject("Worker Live Tenant", "Worker Live Project", ashrclone.Dataset{Name: "Worker Dataset"}, tenantID, projectID)
	if err != nil {
		t.Fatalf("bootstrap: %v", err)
	}

	completedID := "job_complete_" + suffix
	if _, err := repository.EnqueueWorkerJob(tenantID, projectID, "release_gate", "run_complete", nil, ashrclone.EnqueueWorkerJobOptions{JobID: completedID, MaxAttempts: 2}); err != nil {
		t.Fatalf("enqueue completed job: %v", err)
	}
	leased, err := repository.LeaseWorkerJob(tenantID, projectID, "worker_complete", ashrclone.LeaseWorkerJobOptions{LeaseSeconds: 30})
	if err != nil || leased.Result.Job == nil || leased.Result.Job.JobID != completedID {
		t.Fatalf("lease completed job: result=%#v err=%v", leased.Result, err)
	}
	firstExpiry := *leased.Result.Job.LeaseExpiresAt
	heartbeat, err := repository.HeartbeatWorkerJob(tenantID, projectID, completedID, "worker_complete", 1)
	if err != nil {
		t.Fatalf("heartbeat completed job: %v", err)
	}
	if heartbeat.Result.LeaseExpiresAt == nil || heartbeat.Result.LeaseExpiresAt.Before(firstExpiry) {
		t.Fatalf("heartbeat shortened lease: before=%v after=%v", firstExpiry, heartbeat.Result.LeaseExpiresAt)
	}
	completed, err := repository.CompleteWorkerJob(tenantID, projectID, completedID, "worker_complete", ashrclone.JSONMap{"verdict": "pass"}, ashrclone.CompleteWorkerJobOptions{})
	if err != nil || completed.Result.Status != ashrclone.WorkerJobStatusCompleted || completed.Result.ResultSHA256 == "" {
		t.Fatalf("complete job: result=%#v err=%v", completed.Result, err)
	}

	retryID := "job_retry_" + suffix
	if _, err := repository.EnqueueWorkerJob(tenantID, projectID, "release_gate", "run_retry", nil, ashrclone.EnqueueWorkerJobOptions{JobID: retryID, MaxAttempts: 2}); err != nil {
		t.Fatalf("enqueue retry job: %v", err)
	}
	if _, err := repository.LeaseWorkerJob(tenantID, projectID, "worker_retry_1", ashrclone.LeaseWorkerJobOptions{LeaseSeconds: 30}); err != nil {
		t.Fatalf("lease retry job: %v", err)
	}
	retryNow := 0
	retrying, err := repository.FailWorkerJob(tenantID, projectID, retryID, "worker_retry_1", ashrclone.JSONMap{"type": "transient", "message": "retry"}, ashrclone.FailWorkerJobOptions{RetryAfterSeconds: &retryNow})
	if err != nil || retrying.Result.Status != ashrclone.WorkerJobStatusRetrying {
		t.Fatalf("retry job: result=%#v err=%v", retrying.Result, err)
	}
	secondLease, err := repository.LeaseWorkerJob(tenantID, projectID, "worker_retry_2", ashrclone.LeaseWorkerJobOptions{LeaseSeconds: 30})
	if err != nil || secondLease.Result.Job == nil || secondLease.Result.Job.JobID != retryID || secondLease.Result.Job.Attempts != 2 {
		t.Fatalf("second lease: result=%#v err=%v", secondLease.Result, err)
	}
	dead, err := repository.FailWorkerJob(tenantID, projectID, retryID, "worker_retry_2", ashrclone.JSONMap{"type": "permanent", "message": "dead"}, ashrclone.FailWorkerJobOptions{})
	if err != nil || dead.Result.Status != ashrclone.WorkerJobStatusDeadLettered || dead.Result.DeadLetteredAt == nil {
		t.Fatalf("dead-letter failed job: result=%#v err=%v", dead.Result, err)
	}

	crashID := "job_crash_" + suffix
	if _, err := repository.EnqueueWorkerJob(tenantID, projectID, "release_gate", "run_crash", nil, ashrclone.EnqueueWorkerJobOptions{JobID: crashID, MaxAttempts: 1}); err != nil {
		t.Fatalf("enqueue crash job: %v", err)
	}
	if _, err := repository.LeaseWorkerJob(tenantID, projectID, "worker_crashed", ashrclone.LeaseWorkerJobOptions{LeaseSeconds: 300}); err != nil {
		t.Fatalf("lease crash job: %v", err)
	}

	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("open crash simulator: %v", err)
	}
	if _, err := db.ExecContext(context.Background(), `
UPDATE ashr_worker_jobs
SET lease_expires_at = now() - interval '1 second'
WHERE tenant_id = $1 AND project_id = $2 AND job_id = $3
`, tenantID, projectID, crashID); err != nil {
		_ = db.Close()
		t.Fatalf("expire crash lease: %v", err)
	}
	if err := db.Close(); err != nil {
		t.Fatalf("close crash simulator: %v", err)
	}
	if err := repository.Close(); err != nil {
		t.Fatalf("close first repository: %v", err)
	}

	restarted, err := ashrclone.OpenPostgresRepository(dsn)
	if err != nil {
		t.Fatalf("reopen postgres repository: %v", err)
	}
	defer restarted.Close()
	recovered, err := restarted.ListWorkerJobs(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, ashrclone.ListWorkerJobsOptions{Status: ashrclone.WorkerJobStatusDeadLettered})
	if err != nil {
		t.Fatalf("recover expired lease after restart: %v", err)
	}
	crashed := findLiveWorkerJob(recovered.Result.Jobs, crashID)
	if crashed == nil || crashed.Attempts != 1 || crashed.DeadLetteredAt == nil || crashed.AvailableAt != nil {
		t.Fatalf("expired final attempt was not durably dead-lettered: %#v", crashed)
	}
	if crashed.LastError == nil || crashed.LastError.Type != "worker_lease_expired" || crashed.LastError.SHA256 == "" || crashed.LastError.RawPayloadIncluded {
		t.Fatalf("expired final attempt missing public-safe recovery evidence: %#v", crashed)
	}
	empty, err := restarted.LeaseWorkerJob(tenantID, projectID, "worker_after_restart", ashrclone.LeaseWorkerJobOptions{JobType: "release_gate"})
	if err != nil {
		t.Fatalf("lease after restart: %v", err)
	}
	if empty.Result.Leased {
		t.Fatalf("terminal jobs were leased after restart: %#v", empty.Result)
	}
}

func findLiveWorkerJob(jobs []ashrclone.WorkerJob, jobID string) *ashrclone.WorkerJob {
	for index := range jobs {
		if jobs[index].JobID == jobID {
			return &jobs[index]
		}
	}
	return nil
}
