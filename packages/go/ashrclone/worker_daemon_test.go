package ashrclone

import (
	"context"
	"errors"
	"strings"
	"testing"
)

func TestWorkerDaemonRunsBoundedLeaseLoopAndRecordsQuotaAudit(t *testing.T) {
	service := NewMemoryService()
	boot, err := service.BootstrapProject("Tenant", "Daemon", Dataset{Name: "Dataset"}, "tenant_daemon", "project_daemon")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.EnqueueWorkerJob(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, "release_gate", "run_1", JSONMap{"case": "one"}, EnqueueWorkerJobOptions{JobID: "job_daemon_1", MaxAttempts: 2}); err != nil {
		t.Fatal(err)
	}
	if _, err := service.EnqueueWorkerJob(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, "release_gate", "run_2", JSONMap{"case": "two"}, EnqueueWorkerJobOptions{JobID: "job_daemon_2", MaxAttempts: 2}); err != nil {
		t.Fatal(err)
	}

	handled := []string{}
	daemon := WorkerDaemon{
		Repository: service,
		Handler: WorkerJobHandlerFunc(func(ctx context.Context, job WorkerJob) (JSONMap, error) {
			handled = append(handled, job.JobID)
			return JSONMap{"job_id": job.JobID, "verdict": "pass"}, nil
		}),
		Options: WorkerDaemonOptions{TenantID: boot.Result.Tenant.TenantID, ProjectID: boot.Result.Project.ProjectID, LeaseOwnerID: "daemon_a", JobType: "release_gate", MaxJobs: 1, LeaseSeconds: 60},
	}

	summary, err := daemon.Run(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if summary.Leased != 1 || summary.Completed != 1 || summary.Failed != 0 || summary.IdleLeases != 0 || len(summary.Jobs) != 1 {
		t.Fatalf("unexpected daemon summary: %#v", summary)
	}
	if summary.FinishedAt.IsZero() || summary.FinishedAt.Before(summary.StartedAt) {
		t.Fatalf("expected finished_at to be populated after run: %#v", summary)
	}
	if len(handled) != 1 || handled[0] != "job_daemon_1" {
		t.Fatalf("expected one priority job to be handled, got %#v", handled)
	}
	if summary.Jobs[0].Status != WorkerJobStatusCompleted || summary.Jobs[0].ResultSHA256 == "" || summary.Jobs[0].LeaseOwnerID != "" {
		t.Fatalf("expected completed public job record, got %#v", summary.Jobs[0])
	}

	jobs, err := service.ListWorkerJobs(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, ListWorkerJobsOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if jobs.Result.Count != 2 || jobs.Result.Jobs[0].Status != WorkerJobStatusCompleted || jobs.Result.Jobs[1].Status != WorkerJobStatusQueued {
		t.Fatalf("expected bounded daemon to leave second job queued, got %#v", jobs.Result.Jobs)
	}

	usage, err := service.UsageSnapshot(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID)
	if err != nil {
		t.Fatal(err)
	}
	assertUsageTotal(t, usage.Result.OperationTotals, usageOperationWorkerJobEnqueue, 2, 2)
	assertUsageTotal(t, usage.Result.OperationTotals, usageOperationWorkerJobLease, 1, 1)
	assertUsageTotal(t, usage.Result.OperationTotals, usageOperationWorkerJobComplete, 1, 1)

	audit, err := service.AuditLog(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, AuditLogOptions{ActionPrefix: "worker.job"})
	if err != nil {
		t.Fatal(err)
	}
	if audit.Result.Count != 4 {
		t.Fatalf("expected enqueue, enqueue, lease, complete audit events; got %#v", audit.Result.Events)
	}
}

func TestWorkerDaemonFailsJobWithPublicSafeError(t *testing.T) {
	service := NewMemoryService()
	boot, err := service.BootstrapProject("Tenant", "Daemon", Dataset{Name: "Dataset"}, "tenant_daemon_fail", "project_daemon_fail")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.EnqueueWorkerJob(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, "trace_ingest", "run_fail", JSONMap{"case": "fail"}, EnqueueWorkerJobOptions{JobID: "job_daemon_fail", MaxAttempts: 2}); err != nil {
		t.Fatal(err)
	}
	retryAfter := 0
	daemon := WorkerDaemon{
		Repository: service,
		Handler: WorkerJobHandlerFunc(func(ctx context.Context, job WorkerJob) (JSONMap, error) {
			return nil, errors.New("provider failed with token=secret-token and bearer credential")
		}),
		Options: WorkerDaemonOptions{TenantID: boot.Result.Tenant.TenantID, ProjectID: boot.Result.Project.ProjectID, LeaseOwnerID: "daemon_fail", MaxJobs: 1, RetryAfterSeconds: &retryAfter},
	}

	summary, err := daemon.RunOnce(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if summary.Leased != 1 || summary.Failed != 1 || len(summary.Jobs) != 1 {
		t.Fatalf("unexpected failure summary: %#v", summary)
	}
	job := summary.Jobs[0]
	if job.Status != WorkerJobStatusRetrying || job.LastError == nil || job.LastError.RawPayloadIncluded {
		t.Fatalf("expected retrying job with public-safe error hash, got %#v", job)
	}
	if job.LastError.Message == "" || strings.Contains(strings.ToLower(job.LastError.Message), "bearer") || strings.Contains(strings.ToLower(job.LastError.Message), "secret-token") {
		t.Fatalf("expected daemon error to be redacted, got %#v", job.LastError)
	}
}

func assertUsageTotal(t *testing.T, totals []UsageOperationTotal, operation string, units, events int) {
	t.Helper()
	for _, total := range totals {
		if total.Operation == operation {
			if total.Units != units || total.Events != events {
				t.Fatalf("unexpected total for %s: %#v", operation, total)
			}
			return
		}
	}
	t.Fatalf("missing usage total for %s in %#v", operation, totals)
}
