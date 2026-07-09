package ashrclone

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"
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
	if summary.LeaseSeconds != 60 || summary.MaxJobs != 1 || summary.Heartbeat {
		t.Fatalf("expected public-safe daemon options in summary, got %#v", summary)
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

func TestWorkerDaemonHeartbeatsThenCompletesWithPublicSafeMetadata(t *testing.T) {
	service := NewMemoryService()
	boot, err := service.BootstrapProject("Tenant", "Daemon Heartbeat", Dataset{Name: "Dataset"}, "tenant_daemon_heartbeat", "project_daemon_heartbeat")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.EnqueueWorkerJob(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, "release_gate", "run_heartbeat", JSONMap{"secret": "not-returned"}, EnqueueWorkerJobOptions{JobID: "job_daemon_heartbeat", MaxAttempts: 2}); err != nil {
		t.Fatal(err)
	}

	leaseSeconds := 5
	daemon := WorkerDaemon{
		Repository: service,
		Handler: WorkerJobHandlerFunc(func(ctx context.Context, job WorkerJob) (JSONMap, error) {
			time.Sleep(25 * time.Millisecond)
			return JSONMap{"job_id": job.JobID, "payload_sha256": job.PayloadSHA256, "public_safe": true}, nil
		}),
		Options: WorkerDaemonOptions{TenantID: boot.Result.Tenant.TenantID, ProjectID: boot.Result.Project.ProjectID, LeaseOwnerID: "daemon_heartbeat", MaxJobs: 1, LeaseSeconds: leaseSeconds, HeartbeatInterval: time.Millisecond},
	}

	summary, err := daemon.RunOnce(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if summary.Leased != 1 || summary.Completed != 1 || summary.Failed != 0 || summary.Heartbeats == 0 || summary.HeartbeatErrs != 0 || !summary.Heartbeat {
		t.Fatalf("expected heartbeat->complete evidence in summary, got %#v", summary)
	}
	job := summary.Jobs[0]
	if job.Status != WorkerJobStatusCompleted || job.LeaseOwnerID != "" || job.LeaseExpiresAt != nil || job.RawPayloadIncluded || job.PayloadSHA256 == "" || job.ResultSHA256 == "" {
		t.Fatalf("expected completed public-safe job metadata, got %#v", job)
	}

	usage, err := service.UsageSnapshot(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID)
	if err != nil {
		t.Fatal(err)
	}
	assertUsageTotal(t, usage.Result.OperationTotals, usageOperationWorkerJobLease, 1, 1)
	assertUsageTotal(t, usage.Result.OperationTotals, usageOperationWorkerJobComplete, 1, 1)
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
	if summary.Retrying != 1 || summary.DeadLettered != 0 {
		t.Fatalf("expected retry summary, got %#v", summary)
	}
	job := summary.Jobs[0]
	if job.Status != WorkerJobStatusRetrying || job.LastError == nil || job.LastError.RawPayloadIncluded {
		t.Fatalf("expected retrying job with public-safe error hash, got %#v", job)
	}
	if job.LeaseOwnerID != "" || job.LeaseExpiresAt != nil || job.AvailableAt == nil || job.DeadLetteredAt != nil || job.LastError.SHA256 == "" {
		t.Fatalf("expected retry to release lease and preserve public-safe retry metadata, got %#v", job)
	}
	if job.LastError.Message == "" || strings.Contains(strings.ToLower(job.LastError.Message), "bearer") || strings.Contains(strings.ToLower(job.LastError.Message), "secret-token") {
		t.Fatalf("expected daemon error to be redacted, got %#v", job.LastError)
	}
}

func TestWorkerDaemonDeadLettersAfterFinalAttempt(t *testing.T) {
	service := NewMemoryService()
	boot, err := service.BootstrapProject("Tenant", "Daemon Dead Letter", Dataset{Name: "Dataset"}, "tenant_daemon_dead", "project_daemon_dead")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.EnqueueWorkerJob(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, "trace_ingest", "run_dead", JSONMap{"case": "dead"}, EnqueueWorkerJobOptions{JobID: "job_daemon_dead", MaxAttempts: 1}); err != nil {
		t.Fatal(err)
	}

	daemon := WorkerDaemon{
		Repository: service,
		Handler: WorkerJobHandlerFunc(func(ctx context.Context, job WorkerJob) (JSONMap, error) {
			return nil, errors.New("provider failed with password=super-secret")
		}),
		Options: WorkerDaemonOptions{TenantID: boot.Result.Tenant.TenantID, ProjectID: boot.Result.Project.ProjectID, LeaseOwnerID: "daemon_dead", MaxJobs: 1, LeaseSeconds: 30},
	}

	summary, err := daemon.RunOnce(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if summary.Leased != 1 || summary.Failed != 1 || summary.Retrying != 0 || summary.DeadLettered != 1 || len(summary.Jobs) != 1 {
		t.Fatalf("unexpected dead-letter summary: %#v", summary)
	}
	job := summary.Jobs[0]
	if job.Status != WorkerJobStatusDeadLettered || job.LeaseOwnerID != "" || job.LeaseExpiresAt != nil || job.AvailableAt != nil || job.DeadLetteredAt == nil {
		t.Fatalf("expected dead-letter to release lease without retry availability, got %#v", job)
	}
	if job.LastError == nil || job.LastError.RawPayloadIncluded || job.LastError.SHA256 == "" || strings.Contains(strings.ToLower(job.LastError.Message), "super-secret") {
		t.Fatalf("expected public-safe dead-letter error metadata, got %#v", job.LastError)
	}

	usage, err := service.UsageSnapshot(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID)
	if err != nil {
		t.Fatal(err)
	}
	assertUsageTotal(t, usage.Result.OperationTotals, usageOperationWorkerJobFail, 1, 1)
}

func TestWorkerDaemonDeadLettersAfterMaxAttemptsWithPublicSafeSummary(t *testing.T) {
	service := NewMemoryService()
	boot, err := service.BootstrapProject("Tenant", "Daemon", Dataset{Name: "Dataset"}, "tenant_daemon_dead", "project_daemon_dead")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.EnqueueWorkerJob(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, "release_gate", "run_dead", JSONMap{"case": "dead", "api_key": "tp_should_not_escape"}, EnqueueWorkerJobOptions{JobID: "job_daemon_dead", MaxAttempts: 1}); err != nil {
		t.Fatal(err)
	}
	retryAfter := 0
	daemon := WorkerDaemon{
		Repository: service,
		Handler: WorkerJobHandlerFunc(func(ctx context.Context, job WorkerJob) (JSONMap, error) {
			return nil, errors.New("live provider failed with secret=top-secret and bearer token")
		}),
		Options: WorkerDaemonOptions{TenantID: boot.Result.Tenant.TenantID, ProjectID: boot.Result.Project.ProjectID, LeaseOwnerID: "daemon_dead", MaxJobs: 1, LeaseSeconds: 45, RetryAfterSeconds: &retryAfter},
	}

	summary, err := daemon.RunOnce(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if summary.Leased != 1 || summary.Completed != 0 || summary.Failed != 1 || summary.Retrying != 0 || summary.DeadLettered != 1 || summary.LeaseSeconds != 45 || summary.MaxJobs != 1 {
		t.Fatalf("unexpected dead-letter summary: %#v", summary)
	}
	if summary.Heartbeat {
		t.Fatalf("heartbeat should be disabled without interval: %#v", summary)
	}
	job := summary.Jobs[0]
	if job.Status != WorkerJobStatusDeadLettered || job.DeadLetteredAt == nil || job.LastError == nil {
		t.Fatalf("expected dead-lettered job with public error metadata, got %#v", job)
	}
	serialized := strings.ToLower(fmt.Sprintf("%#v", summary))
	for _, forbidden := range []string{"top-secret", "bearer token", "tp_should_not_escape", "secret=", "api_key"} {
		if strings.Contains(serialized, forbidden) {
			t.Fatalf("daemon summary leaked %q: %s", forbidden, serialized)
		}
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
