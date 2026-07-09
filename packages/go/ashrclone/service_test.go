package ashrclone

import (
	"errors"
	"testing"
)

func TestMemoryServiceAPIKeyLifecyclePreflightAndQuota(t *testing.T) {
	service := NewMemoryService()
	if _, err := service.BootstrapProject("Tenant", "Auth", Dataset{Name: "Dataset"}, "tenant_auth", "project_auth"); err != nil {
		t.Fatal(err)
	}

	created, err := service.CreateAPIKey("tenant_auth", "project_auth", CreateAPIKeyOptions{KeyID: "key_submit", Name: "submitter", Scopes: []string{ScopeRunSubmit}, RevealSecret: true})
	if err != nil {
		t.Fatal(err)
	}
	if created.Result.OneTimeSecret == "" || created.Result.APIKey.SecretSHA256 != "" || created.Result.APIKey.SecretPrefix == "" {
		t.Fatalf("expected one-time local test secret with redacted stored hash, got %#v", created.Result)
	}

	verified, err := service.VerifyAPIKeySecret("tenant_auth", "project_auth", "key_submit", created.Result.OneTimeSecret, ScopeRunSubmit)
	if err != nil {
		t.Fatal(err)
	}
	if !verified.Result.Authenticated || verified.Result.SecretValuePresent {
		t.Fatalf("expected local test secret verification, got %#v", verified.Result)
	}

	if _, err := service.PreflightAPIKey(PreflightOptions{TenantID: "tenant_auth", ProjectID: "project_auth", KeyID: "key_submit", Scope: ScopeRunUpload, Operation: "upload_run"}); err == nil {
		t.Fatal("expected missing scope to fail preflight")
	}
	if _, err := service.ConfigureAPIKeyRateLimit("tenant_auth", "project_auth", "key_submit", "sdk_submit", 1); err != nil {
		t.Fatal(err)
	}
	if _, err := service.PreflightAPIKey(PreflightOptions{TenantID: "tenant_auth", ProjectID: "project_auth", KeyID: "key_submit", Scope: ScopeRunSubmit, Operation: "sdk_submit"}); err != nil {
		t.Fatalf("expected first preflight within quota: %v", err)
	}
	first, err := service.SubmitRun("tenant_auth", "project_auth", "dataset_auth", "agent:auth", "run_quota", nil, IdempotencyOptions{Key: "idem_quota", APIKeyID: "key_submit"})
	if err != nil {
		t.Fatal(err)
	}
	replay, err := service.SubmitRun("tenant_auth", "project_auth", "dataset_auth", "agent:auth", "run_quota", nil, IdempotencyOptions{Key: "idem_quota", APIKeyID: "key_submit"})
	if err != nil {
		t.Fatal(err)
	}
	if !replay.IdempotentReplay || replay.Result.RunID != first.Result.RunID {
		t.Fatalf("expected idempotent replay without additional quota, got %#v", replay)
	}
	if _, err := service.PreflightAPIKey(PreflightOptions{TenantID: "tenant_auth", ProjectID: "project_auth", KeyID: "key_submit", Scope: ScopeRunSubmit, Operation: "sdk_submit"}); err == nil {
		t.Fatal("expected quota preflight failure after one submit")
	}
	if _, err := service.SubmitRun("tenant_auth", "project_auth", "dataset_auth", "agent:auth", "run_quota_2", nil, IdempotencyOptions{APIKeyID: "key_submit"}); err == nil {
		t.Fatal("expected service-level quota enforcement before second submit")
	} else {
		var quota QuotaExceededError
		if !errors.As(err, &quota) || quota.Operation != "sdk_submit" {
			t.Fatalf("expected quota_exceeded for sdk_submit, got %T %v", err, err)
		}
	}

	revoked, err := service.RevokeAPIKey("tenant_auth", "project_auth", "key_submit")
	if err != nil {
		t.Fatal(err)
	}
	if !revoked.Result.Revoked || revoked.Result.SecretSHA256 != "" {
		t.Fatalf("expected revoked redacted key record, got %#v", revoked.Result)
	}
}

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

func TestMemoryServiceAuditLogAndReleaseEvidencePacket(t *testing.T) {
	service := NewMemoryService()
	boot, err := service.BootstrapProject("Tenant", "Evidence", Dataset{Name: "Dataset"}, "tenant_evidence", "project_evidence")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.SubmitRun("tenant_evidence", "project_evidence", boot.Result.Dataset.DatasetID, "agent:evidence", "run_evidence", nil, IdempotencyOptions{APIKeyID: "key_evidence"}); err != nil {
		t.Fatal(err)
	}
	if _, err := service.UploadRun("tenant_evidence", "project_evidence", "run_evidence", JSONMap{"score": 0.99}, UploadRunOptions{UploadID: "upload_evidence", APIKeyID: "key_evidence"}); err != nil {
		t.Fatal(err)
	}
	if _, err := service.IngestTrace("tenant_evidence", "project_evidence", "run_evidence", []JSONMap{{"span_id": "span_evidence"}}, IngestTraceOptions{BatchID: "trace_evidence", APIKeyID: "key_evidence"}); err != nil {
		t.Fatal(err)
	}
	if _, err := service.CreateArtifactManifest("tenant_evidence", "project_evidence", "run_evidence", JSONMap{"artifact": "release.json"}, ArtifactManifestOptions{ArtifactID: "artifact_evidence", APIKeyID: "key_evidence"}); err != nil {
		t.Fatal(err)
	}

	audit, err := service.AuditLog("tenant_evidence", "project_evidence", AuditLogOptions{RunID: "run_evidence", ActionPrefix: "artifact", Limit: 1})
	if err != nil {
		t.Fatal(err)
	}
	if audit.Result.Count != 1 || audit.Result.Events[0].Action != "artifact.manifest" || audit.Result.Events[0].TargetID != "run_evidence" {
		t.Fatalf("unexpected filtered audit log: %#v", audit.Result)
	}

	packet, err := service.BuildReleaseEvidencePacket("tenant_evidence", "project_evidence", "run_evidence")
	if err != nil {
		t.Fatal(err)
	}
	if packet.Result.PacketSHA256 == "" || len(packet.Result.Uploads) != 1 || len(packet.Result.TraceBatches) != 1 || len(packet.Result.ArtifactManifests) != 1 || !packet.Result.AuditVerification.Verified {
		t.Fatalf("unexpected release evidence packet: %#v", packet.Result)
	}
	mapped, err := jsonMapFromStruct(packet.Result)
	if err != nil {
		t.Fatal(err)
	}
	verified, err := service.VerifyReleaseEvidencePacket("tenant_evidence", "project_evidence", "run_evidence", mapped)
	if err != nil {
		t.Fatal(err)
	}
	if !verified.Result.Verified || verified.Result.PacketSHA256 == "" {
		t.Fatalf("expected packet to verify: %#v", verified.Result)
	}
	mapped["run_id"] = "run_tampered"
	tampered, err := service.VerifyReleaseEvidencePacket("tenant_evidence", "project_evidence", "run_evidence", mapped)
	if err != nil {
		t.Fatal(err)
	}
	if tampered.Result.Verified || tampered.Result.Reason == "" {
		t.Fatalf("expected tampered packet to fail verification: %#v", tampered.Result)
	}
}
