package releasefoundry

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

var registerWebhookNoConnectDriver sync.Once
var webhookNoConnectOpenCount atomic.Int64

type webhookNoConnectDriver struct{}

func (webhookNoConnectDriver) Open(string) (driver.Conn, error) {
	webhookNoConnectOpenCount.Add(1)
	return nil, errors.New("database connection must not open for an unverified webhook")
}

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

func TestPostgresUnverifiedBillingWebhookRejectsBeforeAnyTransactionOrMutation(t *testing.T) {
	source := readPostgresSource(t)
	start := strings.Index(source, "func (repository *PostgresRepository) IngestBillingWebhook")
	end := strings.Index(source[start:], "func (repository *PostgresRepository) BillingLedger")
	if start < 0 || end < 0 {
		t.Fatal("could not isolate IngestBillingWebhook source")
	}
	body := source[start : start+end]
	reject := strings.Index(body, "return rejectedBillingWebhookEnvelope(event), nil")
	if reject < 0 {
		t.Fatal("unverified billing webhook does not have a fail-closed return")
	}
	for _, mutationMarker := range []string{
		"repository.db.BeginTx",
		"loadIdempotentBillingWebhookReplay",
		"ensurePostgresBillingSaaSScope",
		"ingestPostgresBillingProviderEvent",
		"appendPostgresMutationEvidence",
		"insertIdempotentBillingWebhookResponse",
		"tx.Commit",
	} {
		position := strings.Index(body, mutationMarker)
		if position < 0 {
			t.Fatalf("billing webhook implementation missing expected marker %q", mutationMarker)
		}
		if reject > position {
			t.Fatalf("unverified rejection occurs after mutation marker %q", mutationMarker)
		}
	}
}

func TestPostgresSchemaIncludesFirstSliceTables(t *testing.T) {
	for _, table := range []string{"releasefoundry_tenants", "releasefoundry_projects", "releasefoundry_datasets", "releasefoundry_runs", "releasefoundry_idempotency_ledger"} {
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
		"CREATE TABLE IF NOT EXISTS releasefoundry_worker_jobs",
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
		"releasefoundry_worker_jobs_lease_idx ON releasefoundry_worker_jobs (tenant_id, project_id, status, job_type, priority, available_at, created_at)",
		"releasefoundry_worker_jobs_status_idx ON releasefoundry_worker_jobs (tenant_id, project_id, status, updated_at)",
	} {
		if !strings.Contains(PostgresSchemaSQL, required) {
			t.Fatalf("worker job schema missing %q", required)
		}
	}
}

func TestPostgresWorkerRecoveryWiresAttemptBoundedLeaseExpiry(t *testing.T) {
	source := readPostgresSource(t)
	for _, required := range []string{
		"CASE WHEN attempts >= max_attempts THEN $4 ELSE $5 END",
		"dead_lettered_at = CASE WHEN attempts >= max_attempts THEN $3 ELSE NULL END",
		`"worker.job.lease_expired"`,
		`Type:               "worker_lease_expired"`,
		"SET lease_expires_at = GREATEST(lease_expires_at, $4)",
	} {
		if !strings.Contains(source, required) {
			t.Fatalf("postgres worker recovery missing %q", required)
		}
	}
}

func TestPostgresAuditEventIDSeparatesBatchWorkerRecoveryEvidence(t *testing.T) {
	now := time.Unix(1700000000, 123456000).UTC()
	firstEvidence := postgresMutationEvidence{
		TargetID:       "job_first",
		IdempotencyKey: "idem_first",
		RequestID:      "request_first",
		After:          JSONMap{"status": WorkerJobStatusRetrying},
	}
	secondEvidence := postgresMutationEvidence{
		TargetID:       "job_second",
		IdempotencyKey: "idem_second",
		RequestID:      "request_second",
		After:          JSONMap{"status": WorkerJobStatusDeadLettered},
	}

	firstID, err := postgresAuditEventID("worker.job.lease_expired", firstEvidence, firstEvidence.After, now)
	if err != nil {
		t.Fatal(err)
	}
	firstIDAgain, err := postgresAuditEventID("worker.job.lease_expired", firstEvidence, firstEvidence.After, now)
	if err != nil {
		t.Fatal(err)
	}
	secondID, err := postgresAuditEventID("worker.job.lease_expired", secondEvidence, secondEvidence.After, now)
	if err != nil {
		t.Fatal(err)
	}

	if firstID != firstIDAgain {
		t.Fatalf("audit event ID must be stable, got %q then %q", firstID, firstIDAgain)
	}
	if firstID == secondID {
		t.Fatalf("batch worker recovery evidence collided at the same timestamp: %q", firstID)
	}
}

func TestPostgresSchemaIncludesQuotaUsageLedgerContract(t *testing.T) {
	for _, required := range []string{
		"CREATE TABLE IF NOT EXISTS releasefoundry_quota_ledger",
		"CREATE TABLE IF NOT EXISTS releasefoundry_usage_quota_policies",
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
		"FOREIGN KEY (tenant_id, project_id) REFERENCES releasefoundry_projects(tenant_id, project_id) ON DELETE CASCADE",
		"releasefoundry_quota_ledger_scope_idx ON releasefoundry_quota_ledger (tenant_id, project_id, operation, created_at)",
		"releasefoundry_quota_ledger_run_idx ON releasefoundry_quota_ledger (tenant_id, project_id, run_id, created_at)",
		"releasefoundry_usage_quota_policies_scope_idx ON releasefoundry_usage_quota_policies (tenant_id, project_id, operation, status)",
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
		"CREATE TABLE IF NOT EXISTS releasefoundry_api_key_rate_limits",
		"CREATE TABLE IF NOT EXISTS releasefoundry_api_keys",
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
		"CREATE TABLE IF NOT EXISTS releasefoundry_audit_events",
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
		"FOREIGN KEY (tenant_id, project_id) REFERENCES releasefoundry_projects(tenant_id, project_id) ON DELETE CASCADE",
		"releasefoundry_audit_events_scope_idx ON releasefoundry_audit_events (tenant_id, project_id, action, created_at)",
		"releasefoundry_audit_events_target_idx ON releasefoundry_audit_events (tenant_id, project_id, target_id, created_at)",
	} {
		if !strings.Contains(PostgresSchemaSQL, required) {
			t.Fatalf("audit log schema missing %q", required)
		}
	}
}

func TestPostgresSchemaIncludesCanonicalIdentityContract(t *testing.T) {
	for _, required := range []string{
		"CREATE TABLE IF NOT EXISTS releasefoundry_accounts",
		"account_id TEXT PRIMARY KEY",
		"two_factor_enabled BOOLEAN NOT NULL DEFAULT false",
		"two_factor_methods TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]",
		"CREATE TABLE IF NOT EXISTS releasefoundry_identity_credentials",
		"provider_subject_fingerprint TEXT NOT NULL",
		"UNIQUE (provider, provider_subject_fingerprint)",
		"releasefoundry_identity_credentials_union_idx",
		"CREATE TABLE IF NOT EXISTS releasefoundry_identity_challenges",
		"delivery_target_ciphertext BYTEA NOT NULL",
		"delivery_target_key_id TEXT NOT NULL",
		"secret_hash TEXT NOT NULL",
		"secret_hash_key_id TEXT NOT NULL",
		"CREATE TABLE IF NOT EXISTS releasefoundry_identity_sessions",
		"token_hash TEXT NOT NULL",
		"token_hash_key_id TEXT NOT NULL",
		"CREATE TABLE IF NOT EXISTS releasefoundry_account_organization_memberships",
		"PRIMARY KEY (account_id, tenant_id)",
	} {
		if !strings.Contains(PostgresSchemaSQL, required) {
			t.Fatalf("identity schema missing %q", required)
		}
	}
	for _, forbidden := range []string{"oauth_access_token", "oauth_refresh_token", "session_token TEXT", "secret TEXT"} {
		if strings.Contains(strings.ToLower(PostgresSchemaSQL), strings.ToLower(forbidden)) {
			t.Fatalf("identity schema stores forbidden plaintext field %q", forbidden)
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

func TestPostgresBillingRepositoryWiresSQLBackedMoneySlice(t *testing.T) {
	source := readPostgresSource(t)
	for _, forbidden := range []string{
		`return Envelope[BillingCheckoutPlan]{}, repository.notImplemented("billing.checkout_plan")`,
		`return Envelope[BillingPortalPlan]{}, repository.notImplemented("billing.portal_plan")`,
		`return Envelope[BillingWebhookIngest]{}, repository.notImplemented("billing.webhook_ingest")`,
		`return Envelope[BillingLedger]{}, repository.notImplemented("billing.ledger")`,
	} {
		if strings.Contains(source, forbidden) {
			t.Fatalf("postgres billing method still has placeholder %q", forbidden)
		}
	}
	for _, required := range []string{
		"CREATE TABLE IF NOT EXISTS releasefoundry_billing_checkout_plans",
		"CREATE TABLE IF NOT EXISTS releasefoundry_billing_portal_plans",
		"CONSTRAINT releasefoundry_billing_checkout_public_safe CHECK",
		"CONSTRAINT releasefoundry_billing_portal_public_safe CHECK",
		"FROM ingest_billing_provider_event($1::uuid, $2::uuid",
		"ensurePostgresBillingSaaSScope(ctx, tx, tenantID, projectID, now)",
		"INSERT INTO organizations (id, slug, display_name, status, metadata, created_at, updated_at)",
		"billing webhook payload_sha256 must be a sha256 hex digest",
		"FROM billing_provider_events p",
		"LEFT JOIN billing_ledger_events l",
		"raw_payload_included",
		"secret_value_present",
		"IdempotencyConflictError{Operation: operation, Key: key}",
	} {
		if !strings.Contains(source, required) {
			t.Fatalf("postgres billing SQL slice missing %q", required)
		}
	}
}

func TestPostgresBillingUUIDIsDeterministicAndValid(t *testing.T) {
	first := postgresBillingUUID("org", "tenant_billing")
	second := postgresBillingUUID("org", "tenant_billing")
	if first != second {
		t.Fatalf("expected deterministic billing uuid, got %q then %q", first, second)
	}
	if !looksLikeUUID(first) {
		t.Fatalf("expected uuid shape, got %q", first)
	}
	existing := "11111111-2222-3333-4444-555555555555"
	if postgresBillingUUID("org", existing) != existing {
		t.Fatalf("existing uuid should pass through unchanged")
	}
	if first == postgresBillingUUID("project", "tenant_billing") {
		t.Fatalf("prefix must separate uuid namespaces")
	}
}

func TestPostgresBillingPayloadSHAValidation(t *testing.T) {
	valid := strings.Repeat("a", 64)
	if !looksLikeSHA256Hex(valid) {
		t.Fatalf("expected valid sha256 hex")
	}
	for _, invalid := range []string{"", "abc", strings.Repeat("g", 64), strings.Repeat("A", 64)} {
		if looksLikeSHA256Hex(invalid) {
			t.Fatalf("expected invalid sha256 hex %q", invalid)
		}
	}
}

func TestPostgresBillingWebhookRejectsCallerVerificationBeforeAnyDatabaseAccess(t *testing.T) {
	registerWebhookNoConnectDriver.Do(func() {
		sql.Register("releasefoundry_webhook_no_connect", webhookNoConnectDriver{})
	})
	webhookNoConnectOpenCount.Store(0)
	db, err := sql.Open("releasefoundry_webhook_no_connect", "unused")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	repository := NewPostgresRepository(db)
	result, err := repository.IngestBillingWebhook("tenant_webhook", "project_webhook", BillingWebhookIngest{
		EventID:                "evt_untrusted",
		EventType:              "invoice.paid",
		Provider:               "stripe",
		Mode:                   "test",
		Status:                 "active",
		PayloadSHA256:          strings.Repeat("a", 64),
		SignatureHeaderPresent: true,
		WebhookSecretRef:       "env:STRIPE_WEBHOOK_SECRET",
		Verified:               true,
	}, IdempotencyOptions{Key: "idem_untrusted", APIKeyID: "key_untrusted", RequestID: "request_untrusted"})

	if err != nil {
		t.Fatalf("fail-closed rejection should be a public-safe envelope, got %v", err)
	}
	if result.Status != "rejected" || result.Result.Verified {
		t.Fatalf("untrusted caller verification was not rejected: %#v", result)
	}
	if len(result.Result.Failures) == 0 || result.Result.Failures[len(result.Result.Failures)-1]["reason"] != "provider_specific_verification_required" {
		t.Fatalf("missing provider verification failure: %#v", result.Result.Failures)
	}
	if opens := webhookNoConnectOpenCount.Load(); opens != 0 {
		t.Fatalf("unverified webhook reached database driver %d time(s)", opens)
	}
}

func TestPostgresBillingProviderEventHelperRejectsUnverifiedBeforeSQL(t *testing.T) {
	_, _, err := ingestPostgresBillingProviderEvent(context.Background(), nil, "tenant", "project", BillingWebhookIngest{
		EventID:       "evt_unverified",
		EventType:     "invoice.paid",
		Provider:      "stripe",
		Mode:          "test",
		PayloadSHA256: strings.Repeat("b", 64),
		Verified:      false,
	})
	if err == nil || !strings.Contains(err.Error(), "requires trusted verification") {
		t.Fatalf("expected helper to reject unverified event before SQL, got %v", err)
	}
}

func TestPostgresBillingWebhookFailClosedGuardPrecedesEveryPersistencePath(t *testing.T) {
	source := readPostgresSource(t)
	start := strings.Index(source, "func (repository *PostgresRepository) IngestBillingWebhook")
	if start < 0 {
		t.Fatal("could not find Postgres IngestBillingWebhook")
	}
	remaining := source[start:]
	end := strings.Index(remaining, "func (repository *PostgresRepository) BillingLedger")
	if end < 0 {
		t.Fatal("could not isolate Postgres IngestBillingWebhook")
	}
	method := remaining[:end]
	rejectAt := strings.Index(method, "return rejectedBillingWebhookEnvelope(event), nil")
	if rejectAt < 0 {
		t.Fatal("Postgres webhook ingest has no fail-closed return")
	}
	for _, sideEffect := range []string{
		"BeginTx(",
		"loadIdempotentBillingWebhookReplay(",
		"requireProject(",
		"ensurePostgresBillingSaaSScope(",
		"ingestPostgresBillingProviderEvent(",
		"appendPostgresMutationEvidence(",
		"insertIdempotentBillingWebhookResponse(",
		"tx.Commit(",
	} {
		index := strings.Index(method, sideEffect)
		if index < 0 {
			t.Fatalf("expected persistence marker %q in webhook implementation", sideEffect)
		}
		if index < rejectAt {
			t.Fatalf("webhook persistence marker %q occurs before fail-closed return", sideEffect)
		}
	}
}

func TestPostgresBillingDeterministicArtifactsDoNotLeakSecrets(t *testing.T) {
	request := BillingPlanRequest{
		PlanID:       "Startup",
		BillingCycle: "Yearly",
		CustomerRef:  "cus_public",
		SuccessURL:   "https://app.example/success",
		CancelURL:    "https://app.example/cancel",
		Price:        JSONMap{"lookup_key": "startup", "authorization": "bearer secret"},
		ProviderConfig: JSONMap{
			"provider":   "Stripe",
			"mode":       "test",
			"secret_ref": "env:STRIPE_TEST_REF",
			"raw_secret": "sk_test_should_not_escape",
		},
		Metadata: JSONMap{"token": "raw-token", "safe": "value"},
	}
	providerConfig := publicBillingProviderConfig(request.ProviderConfig)
	price := sanitizedBillingMetadata(request.Price)
	metadata := sanitizedBillingMetadata(request.Metadata)
	fingerprint := mustFingerprint(JSONMap{"tenant_id": "tenant", "project_id": "project", "plan_id": normalizeBillingPlanID(request.PlanID), "billing_cycle": normalizeBillingCycle(request.BillingCycle), "provider": billingProviderFromConfig(providerConfig), "mode": billingModeFromConfig(providerConfig, "deterministic_contract"), "customer_ref": strings.TrimSpace(request.CustomerRef), "price": price, "success_url": strings.TrimSpace(request.SuccessURL), "cancel_url": strings.TrimSpace(request.CancelURL), "idempotency_key": "idem"})
	artifact := BillingCheckoutPlan{SchemaVersion: ControlPlaneSchemaVersion, TenantID: "tenant", ProjectID: "project", PlanID: normalizeBillingPlanID(request.PlanID), BillingCycle: normalizeBillingCycle(request.BillingCycle), CheckoutID: "checkout_" + fingerprint[:16], CheckoutURL: "https://billing.local.releasefoundry.invalid/checkout/" + fingerprint[:24], Mode: billingModeFromConfig(providerConfig, "deterministic_contract"), Provider: billingProviderFromConfig(providerConfig), ProviderConfig: providerConfig, CustomerRef: strings.TrimSpace(request.CustomerRef), Price: price, SuccessURL: strings.TrimSpace(request.SuccessURL), CancelURL: strings.TrimSpace(request.CancelURL), SideEffects: billingSafeSideEffects(), ProviderCalled: false, RealChargePossible: false, PublicSafe: true, RawPayloadIncluded: false, RawSecretsIncluded: false, SecretValuePresent: false, Metadata: metadata, CreatedAt: time.Unix(1700000000, 0).UTC()}
	encoded, err := json.Marshal(artifact)
	if err != nil {
		t.Fatal(err)
	}
	for _, leaked := range []string{"sk_test_should_not_escape", "raw-token", "bearer secret"} {
		if strings.Contains(string(encoded), leaked) {
			t.Fatalf("billing artifact leaked secret %q: %s", leaked, encoded)
		}
	}
	if artifact.ProviderCalled || artifact.RealChargePossible || artifact.RawPayloadIncluded || artifact.RawSecretsIncluded || artifact.SecretValuePresent || !artifact.PublicSafe {
		t.Fatalf("unexpected money-grade safety flags: %#v", artifact)
	}
	if artifact.Provider != "stripe" || artifact.Mode != "test" || artifact.PlanID != "startup" || artifact.BillingCycle != "yearly" {
		t.Fatalf("unexpected normalized billing fields: %#v", artifact)
	}
}
