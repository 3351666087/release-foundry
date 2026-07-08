package ashrclone

import (
	"errors"
	"testing"
)

func TestMemoryServiceIdempotentSubmitReplaysAndConflicts(t *testing.T) {
	service := NewMemoryService()
	boot, err := service.BootstrapProject("Enterprise Tenant", "Release Gate", Dataset{Name: "Calibration"}, "tenant_saas", "project_saas")
	if err != nil {
		t.Fatal(err)
	}
	first, err := service.SubmitRun(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, boot.Result.Dataset.DatasetID, "agent:v1", "run_idem", JSONMap{"purpose": "test"}, IdempotencyOptions{Key: "idem_submit", APIKeyID: "key_idem"})
	if err != nil {
		t.Fatal(err)
	}
	replay, err := service.SubmitRun(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, boot.Result.Dataset.DatasetID, "agent:v1", "run_idem", JSONMap{"purpose": "test"}, IdempotencyOptions{Key: "idem_submit", APIKeyID: "key_idem"})
	if err != nil {
		t.Fatal(err)
	}
	if !replay.IdempotentReplay || replay.Result.RunID != first.Result.RunID {
		t.Fatalf("expected replay of %q, got %#v", first.Result.RunID, replay)
	}
	_, err = service.SubmitRun(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, boot.Result.Dataset.DatasetID, "agent:v2", "run_idem_conflict", nil, IdempotencyOptions{Key: "idem_submit"})
	var conflict IdempotencyConflictError
	if !errors.As(err, &conflict) {
		t.Fatalf("expected idempotency conflict, got %T %v", err, err)
	}
}

func TestMemoryServiceWorkerJobLifecycleRetriesAndCompletes(t *testing.T) {
	service := NewMemoryService()
	boot, err := service.BootstrapProject("Enterprise Tenant", "Worker Queue", Dataset{Name: "Dataset"}, "tenant_worker", "project_worker")
	if err != nil {
		t.Fatal(err)
	}

	first, err := service.EnqueueWorkerJob(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, "release_gate", "run_1", JSONMap{"unsafe": false}, EnqueueWorkerJobOptions{JobID: "job_worker", Priority: 5, MaxAttempts: 2, IdempotencyKey: "idem_worker", RequestID: "req_enqueue"})
	if err != nil {
		t.Fatal(err)
	}
	replay, err := service.EnqueueWorkerJob(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, "release_gate", "run_1", JSONMap{"unsafe": false}, EnqueueWorkerJobOptions{JobID: "job_worker", Priority: 5, MaxAttempts: 2, IdempotencyKey: "idem_worker", RequestID: "req_enqueue"})
	if err != nil {
		t.Fatal(err)
	}
	if !replay.IdempotentReplay || replay.Result.JobID != first.Result.JobID {
		t.Fatalf("expected idempotent worker replay, got %#v", replay)
	}
	if first.Result.PayloadSHA256 == "" || first.Result.RawPayloadIncluded {
		t.Fatalf("expected hashed payload without raw inclusion: %#v", first.Result)
	}

	lease, err := service.LeaseWorkerJob(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, "worker_a", LeaseWorkerJobOptions{LeaseSeconds: 300, JobType: "release_gate"})
	if err != nil {
		t.Fatal(err)
	}
	if !lease.Result.Leased || lease.Result.Job == nil || lease.Result.Job.Attempts != 1 || lease.Result.Job.Status != WorkerJobStatusLeased {
		t.Fatalf("unexpected lease response: %#v", lease.Result)
	}

	retryAfter := 0
	failed, err := service.FailWorkerJob(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, "job_worker", "worker_a", JSONMap{"type": "transient", "message": "try again"}, FailWorkerJobOptions{RetryAfterSeconds: &retryAfter})
	if err != nil {
		t.Fatal(err)
	}
	if failed.Result.Status != WorkerJobStatusRetrying || failed.Result.LastError == nil || failed.Result.LastError.SHA256 == "" || failed.Result.LastError.RawPayloadIncluded {
		t.Fatalf("unexpected failed job: %#v", failed.Result)
	}

	leasedAgain, err := service.LeaseWorkerJob(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, "worker_b", LeaseWorkerJobOptions{LeaseSeconds: 300})
	if err != nil {
		t.Fatal(err)
	}
	if leasedAgain.Result.Job == nil || leasedAgain.Result.Job.Attempts != 2 {
		t.Fatalf("expected retry lease attempt 2, got %#v", leasedAgain.Result)
	}

	completed, err := service.CompleteWorkerJob(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, "job_worker", "worker_b", JSONMap{"verdict": "pass"}, CompleteWorkerJobOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if completed.Result.Status != WorkerJobStatusCompleted || completed.Result.ResultSHA256 == "" || completed.Result.LeaseOwnerID != "" || completed.Result.CompletedAt == nil {
		t.Fatalf("unexpected completed job: %#v", completed.Result)
	}
}

func TestMemoryServiceWorkerJobLeaseExpiryAndDeadLetter(t *testing.T) {
	service := NewMemoryService()
	if _, err := service.BootstrapProject("Tenant", "Worker Queue", Dataset{Name: "Dataset"}, "tenant_worker", "project_worker"); err != nil {
		t.Fatal(err)
	}
	if _, err := service.EnqueueWorkerJob("tenant_worker", "project_worker", "trace_ingest", "run_2", nil, EnqueueWorkerJobOptions{JobID: "job_dead", MaxAttempts: 1}); err != nil {
		t.Fatal(err)
	}
	if _, err := service.LeaseWorkerJob("tenant_worker", "project_worker", "expired_owner", LeaseWorkerJobOptions{LeaseSeconds: 1}); err != nil {
		t.Fatal(err)
	}

	service.mu.Lock()
	job := service.workerJobs["job_dead"]
	expired := job.UpdatedAt.Add(-1 * 1_000_000_000)
	job.LeaseExpiresAt = &expired
	service.workerJobs[job.JobID] = job
	service.mu.Unlock()

	released, err := service.LeaseWorkerJob("tenant_worker", "project_worker", "new_owner", LeaseWorkerJobOptions{LeaseSeconds: 300})
	if err != nil {
		t.Fatal(err)
	}
	if released.Result.Job == nil || released.Result.Job.LeaseOwnerID != "new_owner" || released.Result.Job.Attempts != 2 {
		t.Fatalf("expected expired lease to become leaseable, got %#v", released.Result)
	}
	dead, err := service.FailWorkerJob("tenant_worker", "project_worker", "job_dead", "new_owner", JSONMap{"message": "no more retries"}, FailWorkerJobOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if dead.Result.Status != WorkerJobStatusDeadLettered || dead.Result.DeadLetteredAt == nil || dead.Result.AvailableAt != nil {
		t.Fatalf("expected dead-lettered terminal job, got %#v", dead.Result)
	}
}
