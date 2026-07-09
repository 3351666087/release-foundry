package ashrclone

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"
)

func TestPostgresRepositorySatisfiesBackend(t *testing.T) {
	var _ ControlPlaneBackend = (*PostgresRepository)(nil)
	var _ QuotaRepository = (*PostgresRepository)(nil)
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
		"CREATE TABLE IF NOT EXISTS ashr_usage_quota_policies",
		"tenant_id TEXT NOT NULL",
		"project_id TEXT NOT NULL",
		"usage_event_id TEXT NOT NULL",
		"operation TEXT NOT NULL",
		"meter TEXT NOT NULL",
		"limit_units INTEGER NOT NULL",
		"status TEXT NOT NULL DEFAULT 'active'",
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
		"ashr_usage_quota_policies_scope_idx ON ashr_usage_quota_policies (tenant_id, project_id, operation, status)",
	} {
		if !strings.Contains(PostgresSchemaSQL, required) {
			t.Fatalf("quota usage ledger schema missing %q", required)
		}
	}
}

func TestPostgresRepositoryWiresDurableSaaSQuotaFunction(t *testing.T) {
	source := readPostgresSource(t)
	for _, required := range []string{
		`postgresFunctionExists(ctx, tx, "check_quota_and_insert_usage", 12)`,
		"FROM check_quota_and_insert_usage($1::uuid, $2::uuid, $3, $4, NULL, NULL, $5::uuid, 'go-postgres', $6, $7, $8::jsonb, NULL)",
		"INSERT INTO quota_policies (organization_id, project_id, meter, period, limit_quantity, enforcement_mode, status, effective_from, metadata)",
		"ON CONFLICT (organization_id, project_id, meter, period)",
	} {
		if !strings.Contains(source, required) {
			t.Fatalf("postgres quota wiring missing %q", required)
		}
	}
}

func TestPostgresRepositoryWiresDurableAPIKeyLifecycle(t *testing.T) {
	source := readPostgresSource(t)
	for _, forbidden := range []string{
		`return Envelope[APIKeyCreateResult]{}, repository.notImplemented("create_api_key")`,
		`return Envelope[APIKeyListResult]{}, repository.notImplemented("list_api_keys")`,
		`return Envelope[APIKeyRecord]{}, repository.notImplemented("revoke_api_key")`,
		`return Envelope[APIKeyVerifyResult]{}, repository.notImplemented("verify_api_key_secret")`,
		`return Envelope[APIKeyRateLimit]{}, repository.notImplemented("configure_api_key_rate_limit")`,
		`return Envelope[APIKeyRateLimitSnapshot]{}, repository.notImplemented("api_key_rate_limit_snapshot")`,
		`return Envelope[AuthPreflight]{}, repository.notImplemented("auth.preflight")`,
	} {
		if strings.Contains(source, forbidden) {
			t.Fatalf("postgres API key lifecycle still has placeholder %q", forbidden)
		}
	}
	for _, required := range []string{
		"CREATE TABLE IF NOT EXISTS ashr_api_key_rate_limits",
		"CREATE TABLE IF NOT EXISTS ashr_api_keys",
		"INSERT INTO api_keys (id, organization_id, project_id, name, key_prefix, key_hash, scopes, status, created_at, revoked_at)",
		"secretHash(secret)",
		"redactedAPIKeyRecord(record)",
		"scopeAllowed(record.Scopes, scope)",
		"UPDATE api_keys SET last_used_at",
		"UPDATE api_keys\nSET status = 'revoked'",
		"consumeLocalPostgresAPIKeyRateLimit",
		"APIKeyRateLimitSnapshot{SchemaVersion: ControlPlaneSchemaVersion",
		"AuthPreflight{SchemaVersion: ControlPlaneSchemaVersion",
	} {
		if !strings.Contains(source, required) {
			t.Fatalf("postgres API key lifecycle missing %q", required)
		}
	}
}

func TestGoHTTPSubmitRouteRunsAuthPreflightWithoutPreQuotaConsume(t *testing.T) {
	source := readServerSource(t)
	if !strings.Contains(source, `server.preflightRequest(writer, auth, projectID, ScopeRunSubmit, "")`) {
		t.Fatalf("sdk-submit route must run server-level scope preflight before mutation")
	}
	if strings.Contains(source, `server.preflightRequest(writer, auth, projectID, ScopeRunSubmit, "sdk_submit")`) {
		t.Fatalf("sdk-submit route must not consume/check rate quota before idempotency replay")
	}
}

func readPostgresSource(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve postgres test path")
	}
	contents, err := os.ReadFile(filepath.Join(filepath.Dir(file), "postgres.go"))
	if err != nil {
		t.Fatalf("read postgres source: %v", err)
	}
	return string(contents)
}

func readServerSource(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve server test path")
	}
	contents, err := os.ReadFile(filepath.Join(filepath.Dir(file), "server.go"))
	if err != nil {
		t.Fatalf("read server source: %v", err)
	}
	return string(contents)
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
		{name: "usage snapshot", call: func() error {
			_, err := repository.UsageSnapshot("tenant", "project")
			return err
		}},
		{name: "usage append", call: func() error {
			_, err := repository.AppendQuotaUsage("tenant", "project", QuotaUsageAppend{Operation: "sdk_submit"})
			return err
		}},
		{name: "audit chain verify", call: func() error {
			_, err := repository.VerifyAuditChain("tenant", "project")
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

func TestAuditEventJSONUsesTSCompatibleFields(t *testing.T) {
	event := AuditEvent{SchemaVersion: ControlPlaneSchemaVersion, TenantID: "tenant", ProjectID: "project", AuditEventID: "audit_1", Action: "sdk.submit", PreviousHash: "", EventHash: "abc", CreatedAt: time.Unix(1, 2).UTC(), CreatedAtUnixNS: 1000000002}
	payload, err := json.Marshal(event)
	if err != nil {
		t.Fatal(err)
	}
	encoded := string(payload)
	for _, field := range []string{"schema_version", "tenant_id", "project_id", "audit_event_id", "previous_hash", "event_hash", "created_at", "created_at_unixns"} {
		if !strings.Contains(encoded, `"`+field+`"`) {
			t.Fatalf("audit event JSON missing %s: %s", field, encoded)
		}
	}
}

func TestVerifyPostgresAuditChainRowsAcceptsValidChain(t *testing.T) {
	rows := newFakeAuditRows(t, []AuditEvent{
		newAuditTestEvent(t, "audit_1", "sdk.submit", "", time.Unix(10, 1).UTC()),
	})
	second := newAuditTestEvent(t, "audit_2", "sdk.upload", rows.records[0].EventHash, time.Unix(11, 2).UTC())
	rows.records = append(rows.records, fakeAuditRecordFromEvent(t, second))

	result, err := verifyPostgresAuditChainRows(rows, "tenant", "project", time.Unix(12, 0).UTC())
	if err != nil {
		t.Fatal(err)
	}
	if !result.Verified || result.EventCount != 2 {
		t.Fatalf("verification = %+v", result)
	}
	if result.HeadHash == "" || result.TailHash != second.EventHash {
		t.Fatalf("unexpected chain hashes: %+v", result)
	}
}

func TestVerifyPostgresAuditChainRowsRejectsBrokenPreviousHash(t *testing.T) {
	rows := newFakeAuditRows(t, []AuditEvent{
		newAuditTestEvent(t, "audit_1", "sdk.submit", "not-the-tail", time.Unix(10, 1).UTC()),
	})
	result, err := verifyPostgresAuditChainRows(rows, "tenant", "project", time.Unix(12, 0).UTC())
	if err != nil {
		t.Fatal(err)
	}
	if result.Verified || !strings.Contains(result.FirstInvalidReason, "previous_hash mismatch") {
		t.Fatalf("expected previous_hash mismatch, got %+v", result)
	}
}

func TestVerifyPostgresAuditChainRowsRejectsTamperedEventHash(t *testing.T) {
	event := newAuditTestEvent(t, "audit_1", "sdk.submit", "", time.Unix(10, 1).UTC())
	event.EventHash = "tampered"
	rows := newFakeAuditRows(t, []AuditEvent{event})
	result, err := verifyPostgresAuditChainRows(rows, "tenant", "project", time.Unix(12, 0).UTC())
	if err != nil {
		t.Fatal(err)
	}
	if result.Verified || !strings.Contains(result.FirstInvalidReason, "event_hash mismatch") {
		t.Fatalf("expected event_hash mismatch, got %+v", result)
	}
}

func TestPostgresAuditEventHashUsesPersistedTimestampPrecision(t *testing.T) {
	createdAt := time.Unix(10, 123456789).UTC()
	event := newAuditTestEvent(t, "audit_1", "sdk.submit", "", createdAt.Truncate(time.Microsecond))
	readBack := event
	readBack.CreatedAt = createdAt.Truncate(time.Microsecond)
	hash, err := postgresAuditEventHash(readBack)
	if err != nil {
		t.Fatal(err)
	}
	if hash != event.EventHash {
		t.Fatalf("hash changed after timestamptz precision round trip")
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

type fakeAuditRecord struct {
	AuditEvent
	afterPayload []byte
}

type fakeAuditRows struct {
	t       *testing.T
	records []fakeAuditRecord
	index   int
}

func newFakeAuditRows(t *testing.T, events []AuditEvent) *fakeAuditRows {
	t.Helper()
	rows := &fakeAuditRows{t: t, index: -1}
	for _, event := range events {
		rows.records = append(rows.records, fakeAuditRecordFromEvent(t, event))
	}
	return rows
}

func (rows *fakeAuditRows) Next() bool {
	rows.index++
	return rows.index < len(rows.records)
}

func (rows *fakeAuditRows) Err() error { return nil }

func (rows *fakeAuditRows) Scan(dest ...any) error {
	record := rows.records[rows.index]
	values := []any{record.TenantID, record.ProjectID, record.AuditEventID, record.Action, record.TargetID, record.APIKeyID, record.IdempotencyKey, record.RequestID, record.PreviousHash, record.EventHash, record.afterPayload, record.CreatedAt}
	for index, value := range values {
		switch target := dest[index].(type) {
		case *string:
			*target = value.(string)
		case *[]byte:
			*target = append((*target)[:0], value.([]byte)...)
		case *time.Time:
			*target = value.(time.Time)
		default:
			rows.t.Fatalf("unsupported scan target %T", target)
		}
	}
	return nil
}

func newAuditTestEvent(t *testing.T, auditEventID, action, previousHash string, createdAt time.Time) AuditEvent {
	t.Helper()
	event := AuditEvent{SchemaVersion: ControlPlaneSchemaVersion, TenantID: "tenant", ProjectID: "project", AuditEventID: auditEventID, Action: action, TargetID: "target", APIKeyID: "key", IdempotencyKey: "idem", RequestID: "request", PreviousHash: previousHash, After: JSONMap{"target_id": "target"}, CreatedAt: createdAt.UTC()}
	event.CreatedAtUnixNS = event.CreatedAt.UnixNano()
	hash, err := postgresAuditEventHash(event)
	if err != nil {
		t.Fatal(err)
	}
	event.EventHash = hash
	return event
}

func fakeAuditRecordFromEvent(t *testing.T, event AuditEvent) fakeAuditRecord {
	t.Helper()
	payload, err := jsonBytes(defaultMap(event.After))
	if err != nil {
		t.Fatal(err)
	}
	return fakeAuditRecord{AuditEvent: event, afterPayload: payload}
}
