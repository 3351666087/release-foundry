package ashrclone

import (
	"errors"
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
	}
	for _, check := range checks {
		err := check.call()
		if err == nil || !strings.Contains(err.Error(), "db is required") {
			t.Fatalf("%s: expected db validation error, got %v", check.name, err)
		}
	}
}

func TestPostgresRepositoryRemainingOperationsAreExplicitlyUnimplemented(t *testing.T) {
	repository := NewPostgresRepository(nil)
	checks := []struct {
		operation string
		call      func() error
	}{
		{operation: "run.upload", call: func() error {
			_, err := repository.UploadRun("tenant", "project", "run", JSONMap{"ok": true}, UploadRunOptions{})
			return err
		}},
		{operation: "trace.ingest", call: func() error {
			_, err := repository.IngestTrace("tenant", "project", "run", []JSONMap{{"event": "ok"}}, IngestTraceOptions{})
			return err
		}},
		{operation: "artifact.manifest.create", call: func() error {
			_, err := repository.CreateArtifactManifest("tenant", "project", "run", JSONMap{"artifact": "ok"}, ArtifactManifestOptions{})
			return err
		}},
		{operation: "artifact.manifest.list", call: func() error {
			_, err := repository.ListArtifactManifests("tenant", "project", "run")
			return err
		}},
	}

	for _, check := range checks {
		err := check.call()
		if !errors.Is(err, ErrPostgresRepositoryNotImplemented) {
			t.Fatalf("%s: expected not implemented error, got %v", check.operation, err)
		}
		if !strings.Contains(err.Error(), check.operation) {
			t.Fatalf("%s: error should name operation, got %v", check.operation, err)
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
