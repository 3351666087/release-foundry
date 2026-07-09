package ashrclone

import (
	"strings"
	"testing"
)

func TestPostgresRepositorySatisfiesBackend(t *testing.T) {
	var _ ControlPlaneBackend = (*PostgresRepository)(nil)
}

func TestPostgresRepositoryCloseWithoutDB(t *testing.T) {
	repository := NewPostgresRepository(nil)
	if err := repository.Close(); err != nil {
		t.Fatalf("close nil db: %v", err)
	}
}

func TestPostgresSchemaIncludesFirstSliceTables(t *testing.T) {
	for _, table := range []string{"ashr_tenants", "ashr_projects", "ashr_datasets", "ashr_runs", "ashr_idempotency_ledger"} {
		if !strings.Contains(PostgresSchemaSQL, table) {
			t.Fatalf("schema missing %s", table)
		}
	}
	if !strings.Contains(PostgresSchemaSQL, "PRIMARY KEY (operation, tenant_id, project_id, key)") {
		t.Fatalf("schema missing idempotency ledger primary key")
	}
}

func TestPostgresSchemaIncludesDurableWorkerJobContract(t *testing.T) {
	for _, required := range []string{
		"CREATE TABLE IF NOT EXISTS ashr_worker_jobs",
		"job_id TEXT NOT NULL",
		"job_type TEXT NOT NULL",
		"payload_sha256 TEXT NOT NULL",
		"status TEXT NOT NULL",
		"priority INTEGER NOT NULL DEFAULT 100",
		"attempts INTEGER NOT NULL DEFAULT 0",
		"max_attempts INTEGER NOT NULL DEFAULT 3",
		"lease_owner_id TEXT NOT NULL DEFAULT ''",
		"lease_expires_at TIMESTAMPTZ",
		"available_at TIMESTAMPTZ",
		"last_error JSONB",
		"result_sha256 TEXT NOT NULL DEFAULT ''",
		"idempotency_key TEXT NOT NULL DEFAULT ''",
		"request_id TEXT NOT NULL DEFAULT ''",
		"completed_at TIMESTAMPTZ",
		"dead_lettered_at TIMESTAMPTZ",
		"PRIMARY KEY (tenant_id, project_id, job_id)",
		"ashr_worker_jobs_lease_idx ON ashr_worker_jobs (tenant_id, project_id, status, job_type, priority, available_at, created_at)",
		"ashr_worker_jobs_status_idx ON ashr_worker_jobs (tenant_id, project_id, status, updated_at)",
	} {
		if !strings.Contains(PostgresSchemaSQL, required) {
			t.Fatalf("worker job schema missing %q", required)
		}
	}
}

func TestPostgresSchemaIncludesQuotaUsageLedgerContract(t *testing.T) {
	for _, required := range []string{
		"CREATE TABLE IF NOT EXISTS ashr_quota_ledger",
		"tenant_id TEXT NOT NULL",
		"project_id TEXT NOT NULL",
		"usage_event_id TEXT NOT NULL",
		"operation TEXT NOT NULL",
		"units INTEGER NOT NULL DEFAULT 1",
		"api_key_id TEXT NOT NULL DEFAULT ''",
		"idempotency_key TEXT NOT NULL DEFAULT ''",
		"request_id TEXT NOT NULL DEFAULT ''",
		"run_id TEXT NOT NULL DEFAULT ''",
		"target_id TEXT NOT NULL DEFAULT ''",
		"created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
		"PRIMARY KEY (tenant_id, project_id, usage_event_id)",
		"FOREIGN KEY (tenant_id, project_id) REFERENCES ashr_projects(tenant_id, project_id) ON DELETE CASCADE",
		"ashr_quota_ledger_scope_idx ON ashr_quota_ledger (tenant_id, project_id, operation, created_at)",
		"ashr_quota_ledger_run_idx ON ashr_quota_ledger (tenant_id, project_id, run_id, created_at)",
	} {
		if !strings.Contains(PostgresSchemaSQL, required) {
			t.Fatalf("quota usage ledger schema missing %q", required)
		}
	}
}

func TestPostgresSchemaIncludesAuditLogHashChainContract(t *testing.T) {
	for _, required := range []string{
		"CREATE TABLE IF NOT EXISTS ashr_audit_events",
		"tenant_id TEXT NOT NULL",
		"project_id TEXT NOT NULL",
		"audit_event_id TEXT NOT NULL",
		"action TEXT NOT NULL",
		"target_id TEXT NOT NULL DEFAULT ''",
		"api_key_id TEXT NOT NULL DEFAULT ''",
		"idempotency_key TEXT NOT NULL DEFAULT ''",
		"request_id TEXT NOT NULL DEFAULT ''",
		"previous_hash TEXT NOT NULL DEFAULT ''",
		"event_hash TEXT NOT NULL",
		"after_json JSONB NOT NULL DEFAULT '{}'::jsonb",
		"created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
		"PRIMARY KEY (tenant_id, project_id, audit_event_id)",
		"FOREIGN KEY (tenant_id, project_id) REFERENCES ashr_projects(tenant_id, project_id) ON DELETE CASCADE",
		"ashr_audit_events_scope_idx ON ashr_audit_events (tenant_id, project_id, action, created_at)",
		"ashr_audit_events_target_idx ON ashr_audit_events (tenant_id, project_id, target_id, created_at)",
	} {
		if !strings.Contains(PostgresSchemaSQL, required) {
			t.Fatalf("audit log schema missing %q", required)
		}
	}
}

func TestPostgresRepositoryRequiresDBForImplementedOperations(t *testing.T) {
	repository := NewPostgresRepository(nil)
	checks := []struct {
		name string
		call func() error
	}{
		{name: "bootstrap", call: func() error {
			_, err := repository.BootstrapProject("Tenant", "Project", Dataset{Name: "Dataset"}, "tenant", "project")
			return err
		}},
		{name: "submit", call: func() error {
			_, err := repository.SubmitRun("tenant", "project", "dataset", "agent:v1", "run", nil, IdempotencyOptions{Key: "idem"})
			return err
		}},
		{name: "worker enqueue", call: func() error {
			_, err := repository.EnqueueWorkerJob("tenant", "project", "job", "target", nil, EnqueueWorkerJobOptions{})
			return err
		}},
		{name: "worker lease", call: func() error {
			_, err := repository.LeaseWorkerJob("tenant", "project", "worker", LeaseWorkerJobOptions{})
			return err
		}},
		{name: "worker heartbeat", call: func() error {
			_, err := repository.HeartbeatWorkerJob("tenant", "project", "job", "worker", 300)
			return err
		}},
		{name: "worker complete", call: func() error {
			_, err := repository.CompleteWorkerJob("tenant", "project", "job", "worker", JSONMap{"ok": true}, CompleteWorkerJobOptions{})
			return err
		}},
		{name: "worker fail", call: func() error {
			_, err := repository.FailWorkerJob("tenant", "project", "job", "worker", JSONMap{"message": "retry"}, FailWorkerJobOptions{})
			return err
		}},
		{name: "worker list", call: func() error {
			_, err := repository.ListWorkerJobs("tenant", "project", ListWorkerJobsOptions{})
			return err
		}},
		{name: "run upload", call: func() error {
			_, err := repository.UploadRun("tenant", "project", "run", JSONMap{"ok": true}, UploadRunOptions{})
			return err
		}},
		{name: "trace ingest", call: func() error {
			_, err := repository.IngestTrace("tenant", "project", "run", []JSONMap{{"event": "ok"}}, IngestTraceOptions{})
			return err
		}},
		{name: "artifact create", call: func() error {
			_, err := repository.CreateArtifactManifest("tenant", "project", "run", JSONMap{"artifact": "ok"}, ArtifactManifestOptions{})
			return err
		}},
		{name: "artifact list", call: func() error {
			_, err := repository.ListArtifactManifests("tenant", "project", "run")
			return err
		}},
	}
	for _, check := range checks {
		err := check.call()
		if err == nil || !strings.Contains(err.Error(), "db is required") {
			t.Fatalf("%s: expected db validation error, got %v", check.name, err)
		}
	}
}

func TestMigratePostgresRequiresDB(t *testing.T) {
	if err := MigratePostgres(nil, nil); err == nil || !strings.Contains(err.Error(), "db is required") {
		t.Fatalf("expected db validation error, got %v", err)
	}
}

func TestOpenPostgresRepositoryRequiresDSN(t *testing.T) {
	_, err := OpenPostgresRepository("  ")
	if err == nil {
		t.Fatal("expected DSN validation error")
	}
}
