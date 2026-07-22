package ashrclone

import (
	"context"
	"database/sql"
	"errors"
	"regexp"
	"strings"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/lib/pq"
)

func TestProviderDispatchSchemaContract(t *testing.T) {
	for _, required := range []string{
		"CREATE TABLE IF NOT EXISTS ashr_provider_dispatches",
		"request_fingerprint TEXT NOT NULL CHECK (length(request_fingerprint) = 64)",
		"fencing_token BIGINT NOT NULL DEFAULT 0",
		"'indeterminate','reconciling'",
		"ashr_provider_dispatch_lease_shape",
		"ashr_provider_dispatch_terminal_proof",
		"ashr_provider_dispatch_claim_idx",
		"ashr_provider_dispatch_lease_idx",
		"ashr_provider_dispatch_provider_request_idx",
		"ALTER TABLE ashr_provider_dispatches ENABLE ROW LEVEL SECURITY",
		"ALTER TABLE ashr_provider_dispatches FORCE ROW LEVEL SECURITY",
		"app.a1_organization_id",
		"app.a1_project_id",
		"tenant_id::text = NULLIF(current_setting('app.a1_organization_id', true), '')",
		"project_id::text = NULLIF(current_setting('app.a1_project_id', true), '')",
		"USING (",
		"WITH CHECK (",
	} {
		if !strings.Contains(PostgresSchemaSQL, required) {
			t.Fatalf("provider dispatch schema missing %q", required)
		}
	}
}

func TestClaimProviderDispatchHonorsPreCancelledContext(t *testing.T) {
	repository, mock, closeDB := newProviderDispatchMock(t)
	defer closeDB()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_, err := repository.ClaimProviderDispatchContext(ctx, "tenant", "project", "worker", ClaimProviderDispatchOptions{})
	if !errors.Is(err, ErrProviderDispatchCancelled) {
		t.Fatalf("expected cancelled error, got %v", err)
	}
	assertProviderDispatchExpectations(t, mock)
}

func TestClaimProviderDispatchRetriesSerializationFailure(t *testing.T) {
	repository, mock, closeDB := newProviderDispatchMock(t)
	defer closeDB()
	now := time.Unix(1700000000, 0).UTC()
	expiry := now.Add(30 * time.Second)
	repository.now = func() time.Time { return now }

	mock.ExpectBegin()
	mock.ExpectExec("SELECT set_config").
		WithArgs("tenant", "project").
		WillReturnError(&pq.Error{Code: "40001", Message: "secret table detail"})
	mock.ExpectRollback()
	mock.ExpectBegin()
	expectProject(mock)
	mock.ExpectQuery("WITH candidate AS").
		WillReturnRows(providerDispatchRows(now, "dispatch-1", strings.Repeat("a", 64), ProviderDispatchClaimed, 1, 1, "worker", &expiry, "", ""))
	mock.ExpectCommit()

	result, err := repository.ClaimProviderDispatchContext(context.Background(), "tenant", "project", "worker", ClaimProviderDispatchOptions{LeaseSeconds: 30})
	if err != nil {
		t.Fatal(err)
	}
	if !result.Result.Claimed || result.Result.Dispatch.FencingToken != 1 {
		t.Fatalf("unexpected retry result: %#v", result.Result)
	}
	assertProviderDispatchExpectations(t, mock)
}

func TestClaimProviderDispatchDeadlineDuringRetryBackoff(t *testing.T) {
	repository, mock, closeDB := newProviderDispatchMock(t)
	defer closeDB()
	mock.ExpectBegin()
	mock.ExpectExec("SELECT set_config").
		WithArgs("tenant", "project").
		WillReturnError(&pq.Error{Code: "40001", Message: "do not expose"})
	mock.ExpectRollback()
	ctx, cancel := context.WithTimeout(context.Background(), time.Millisecond)
	defer cancel()

	_, err := repository.ClaimProviderDispatchContext(ctx, "tenant", "project", "worker", ClaimProviderDispatchOptions{})
	if !errors.Is(err, ErrProviderDispatchDeadline) {
		t.Fatalf("expected deadline error, got %v", err)
	}
	if strings.Contains(err.Error(), "do not expose") {
		t.Fatalf("driver detail leaked: %v", err)
	}
	assertProviderDispatchExpectations(t, mock)
}

func TestClaimProviderDispatchDeadlockExhaustionIsSafeContention(t *testing.T) {
	repository, mock, closeDB := newProviderDispatchMock(t)
	defer closeDB()
	for attempt := 0; attempt < providerDispatchTransactionAttempts; attempt++ {
		mock.ExpectBegin()
		mock.ExpectExec("SELECT set_config").
			WithArgs("tenant", "project").
			WillReturnError(&pq.Error{Code: "40P01", Message: "relation ashr_provider_dispatches"})
		mock.ExpectRollback()
	}

	_, err := repository.ClaimProviderDispatchContext(context.Background(), "tenant", "project", "worker", ClaimProviderDispatchOptions{})
	if !errors.Is(err, ErrProviderDispatchContention) {
		t.Fatalf("expected contention error, got %v", err)
	}
	if strings.Contains(err.Error(), "relation") || strings.Contains(err.Error(), "ashr_provider_dispatches") {
		t.Fatalf("database detail leaked: %v", err)
	}
	assertProviderDispatchExpectations(t, mock)
}

func TestClaimProviderDispatchCommitFailureIsIndeterminate(t *testing.T) {
	repository, mock, closeDB := newProviderDispatchMock(t)
	defer closeDB()
	now := time.Unix(1700000000, 0).UTC()
	expiry := now.Add(30 * time.Second)
	repository.now = func() time.Time { return now }
	mock.ExpectBegin()
	expectProject(mock)
	mock.ExpectQuery("WITH candidate AS").
		WillReturnRows(providerDispatchRows(now, "dispatch-1", strings.Repeat("a", 64), ProviderDispatchClaimed, 1, 1, "worker", &expiry, "", ""))
	mock.ExpectCommit().WillReturnError(errors.New("password=secret host=private"))

	_, err := repository.ClaimProviderDispatch("tenant", "project", "worker", ClaimProviderDispatchOptions{LeaseSeconds: 30})
	if !errors.Is(err, ErrProviderDispatchIndeterminate) {
		t.Fatalf("expected indeterminate error, got %v", err)
	}
	if strings.Contains(err.Error(), "password") || strings.Contains(err.Error(), "private") {
		t.Fatalf("commit detail leaked: %v", err)
	}
	assertProviderDispatchExpectations(t, mock)
}

func TestSubmitProviderDispatchSameFingerprintReplays(t *testing.T) {
	repository, mock, closeDB := newProviderDispatchMock(t)
	defer closeDB()
	now := time.Unix(1700000000, 0).UTC()
	repository.now = func() time.Time { return now }
	request := JSONMap{"model": "qwen", "input_sha256": strings.Repeat("a", 64)}
	requestSHA, err := fingerprint(request)
	if err != nil {
		t.Fatal(err)
	}
	mock.ExpectBegin()
	expectProject(mock)
	mock.ExpectExec("INSERT INTO ashr_provider_dispatches").
		WithArgs("tenant", "project", "dispatch-1", "qwen", "chat", requestSHA, ProviderDispatchPending, now).
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectQuery("SELECT "+regexp.QuoteMeta(providerDispatchColumns)).
		WithArgs("tenant", "project", "dispatch-1").
		WillReturnRows(providerDispatchRows(now, "dispatch-1", requestSHA, ProviderDispatchCompleted, 1, 3, "", nil, strings.Repeat("b", 64), strings.Repeat("c", 64)))
	mock.ExpectCommit()

	result, err := repository.SubmitProviderDispatch("tenant", "project", "qwen", "chat", request, SubmitProviderDispatchOptions{DispatchID: "dispatch-1"})
	if err != nil {
		t.Fatal(err)
	}
	if result.Result.DispatchID != "dispatch-1" || result.Result.RequestFingerprint != requestSHA {
		t.Fatalf("unexpected replay: %#v", result.Result)
	}
	assertProviderDispatchExpectations(t, mock)
}

func TestSubmitProviderDispatchFingerprintConflict(t *testing.T) {
	repository, mock, closeDB := newProviderDispatchMock(t)
	defer closeDB()
	now := time.Unix(1700000000, 0).UTC()
	repository.now = func() time.Time { return now }
	request := JSONMap{"model": "qwen", "prompt": "new"}
	requestSHA, _ := fingerprint(request)
	existingSHA := strings.Repeat("d", 64)
	mock.ExpectBegin()
	expectProject(mock)
	mock.ExpectExec("INSERT INTO ashr_provider_dispatches").
		WithArgs("tenant", "project", "dispatch-1", "qwen", "chat", requestSHA, ProviderDispatchPending, now).
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectQuery("SELECT "+regexp.QuoteMeta(providerDispatchColumns)).
		WithArgs("tenant", "project", "dispatch-1").
		WillReturnRows(providerDispatchRows(now, "dispatch-1", existingSHA, ProviderDispatchPending, 0, 0, "", nil, "", ""))
	mock.ExpectRollback()

	_, err := repository.SubmitProviderDispatch("tenant", "project", "qwen", "chat", request, SubmitProviderDispatchOptions{DispatchID: "dispatch-1"})
	if !errors.Is(err, ErrProviderDispatchConflict) {
		t.Fatalf("expected conflict, got %v", err)
	}
	assertProviderDispatchExpectations(t, mock)
}

func TestClaimProviderDispatchIncrementsFence(t *testing.T) {
	repository, mock, closeDB := newProviderDispatchMock(t)
	defer closeDB()
	now := time.Unix(1700000000, 0).UTC()
	expiry := now.Add(30 * time.Second)
	repository.now = func() time.Time { return now }
	mock.ExpectBegin()
	expectProject(mock)
	mock.ExpectQuery("WITH candidate AS").
		WithArgs("tenant", "project", ProviderDispatchPending, "qwen", "chat", now,
			ProviderDispatchClaimed, ProviderDispatchClaimed, "worker-1", expiry, false).
		WillReturnRows(providerDispatchRows(now, "dispatch-1", strings.Repeat("a", 64), ProviderDispatchClaimed, 1, 1, "worker-1", &expiry, "", ""))
	mock.ExpectCommit()

	result, err := repository.ClaimProviderDispatch("tenant", "project", "worker-1", ClaimProviderDispatchOptions{Provider: "qwen", Operation: "chat", LeaseSeconds: 30})
	if err != nil {
		t.Fatal(err)
	}
	if !result.Result.Claimed || result.Result.Dispatch.FencingToken != 1 {
		t.Fatalf("unexpected claim: %#v", result.Result)
	}
	assertProviderDispatchExpectations(t, mock)
}

func TestStaleProviderDispatchFenceCannotHeartbeat(t *testing.T) {
	repository, mock, closeDB := newProviderDispatchMock(t)
	defer closeDB()
	now := time.Unix(1700000000, 0).UTC()
	repository.now = func() time.Time { return now }
	mock.ExpectBegin()
	expectProject(mock)
	mock.ExpectQuery("UPDATE ashr_provider_dispatches").
		WillReturnError(sql.ErrNoRows)
	mock.ExpectRollback()

	_, err := repository.HeartbeatProviderDispatch("tenant", "project", "dispatch-1", "stale-worker", 1, 30)
	if !errors.Is(err, ErrProviderDispatchFence) {
		t.Fatalf("expected fence error, got %v", err)
	}
	assertProviderDispatchExpectations(t, mock)
}

func TestCompleteProviderDispatchRequiresProof(t *testing.T) {
	repository := NewPostgresRepository(nil)
	_, err := repository.CompleteProviderDispatch("tenant", "project", "dispatch", "worker", 1, CompleteProviderDispatchOptions{})
	if err == nil || !strings.Contains(err.Error(), "terminal proof is required") {
		t.Fatalf("expected proof validation, got %v", err)
	}
}

func TestCompletedProviderDispatchProofIsImmutable(t *testing.T) {
	repository, mock, closeDB := newProviderDispatchMock(t)
	defer closeDB()
	now := time.Unix(1700000000, 0).UTC()
	proof := JSONMap{"provider_status": "succeeded", "receipt": "receipt-1"}
	response := JSONMap{"output_sha256": strings.Repeat("a", 64)}
	proofSHA, _ := fingerprint(proof)
	responseSHA, _ := fingerprint(response)
	mock.ExpectBegin()
	expectProject(mock)
	mock.ExpectQuery("SELECT "+regexp.QuoteMeta(providerDispatchColumns)).
		WithArgs("tenant", "project", "dispatch-1").
		WillReturnRows(providerDispatchRows(now, "dispatch-1", strings.Repeat("b", 64), ProviderDispatchCompleted, 1, 4, "", nil, proofSHA, responseSHA))
	mock.ExpectCommit()

	result, err := repository.CompleteProviderDispatch("tenant", "project", "dispatch-1", "old-worker", 2, CompleteProviderDispatchOptions{Proof: proof, Response: response})
	if err != nil || result.Result.TerminalProofSHA256 != proofSHA {
		t.Fatalf("identical terminal replay failed: result=%#v err=%v", result.Result, err)
	}

	mock.ExpectBegin()
	expectProject(mock)
	mock.ExpectQuery("SELECT "+regexp.QuoteMeta(providerDispatchColumns)).
		WithArgs("tenant", "project", "dispatch-1").
		WillReturnRows(providerDispatchRows(now, "dispatch-1", strings.Repeat("b", 64), ProviderDispatchCompleted, 1, 4, "", nil, proofSHA, responseSHA))
	mock.ExpectRollback()
	_, err = repository.CompleteProviderDispatch("tenant", "project", "dispatch-1", "old-worker", 2, CompleteProviderDispatchOptions{
		Proof:    JSONMap{"provider_status": "succeeded", "receipt": "different"},
		Response: response,
	})
	if !errors.Is(err, ErrProviderDispatchConflict) {
		t.Fatalf("expected immutable proof conflict, got %v", err)
	}
	assertProviderDispatchExpectations(t, mock)
}

func TestIndeterminateDispatchCanBeClaimedForReconciliation(t *testing.T) {
	repository, mock, closeDB := newProviderDispatchMock(t)
	defer closeDB()
	now := time.Unix(1700000000, 0).UTC()
	expiry := now.Add(time.Minute)
	repository.now = func() time.Time { return now }
	mock.ExpectBegin()
	expectProject(mock)
	mock.ExpectQuery("WITH candidate AS").
		WithArgs("tenant", "project", ProviderDispatchIndeterminate, "", "", now,
			ProviderDispatchReconciling, ProviderDispatchReconciling, "reconciler", expiry, true).
		WillReturnRows(providerDispatchRows(now, "dispatch-1", strings.Repeat("a", 64), ProviderDispatchReconciling, 2, 2, "reconciler", &expiry, "", ""))
	mock.ExpectCommit()

	result, err := repository.ClaimProviderDispatchReconciliation("tenant", "project", "reconciler", ReconcileProviderDispatchOptions{LeaseSeconds: 60})
	if err != nil {
		t.Fatal(err)
	}
	if result.Result.Dispatch.Status != ProviderDispatchReconciling || result.Result.Dispatch.FencingToken != 2 {
		t.Fatalf("unexpected reconciliation claim: %#v", result.Result.Dispatch)
	}
	assertProviderDispatchExpectations(t, mock)
}

func newProviderDispatchMock(t *testing.T) (*PostgresRepository, sqlmock.Sqlmock, func()) {
	t.Helper()
	db, mock, err := sqlmock.New(sqlmock.QueryMatcherOption(sqlmock.QueryMatcherRegexp))
	if err != nil {
		t.Fatal(err)
	}
	return NewPostgresRepository(db), mock, func() { _ = db.Close() }
}

func expectProject(mock sqlmock.Sqlmock) {
	mock.ExpectExec("SELECT set_config").
		WithArgs("tenant", "project").
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery("SELECT 1 FROM ashr_projects").
		WithArgs("tenant", "project").
		WillReturnRows(sqlmock.NewRows([]string{"exists"}).AddRow(1))
}

func providerDispatchRows(
	now time.Time, dispatchID, requestSHA, status string, attempts int, fence int64,
	owner string, expiry *time.Time, proofSHA, responseSHA string,
) *sqlmock.Rows {
	return sqlmock.NewRows([]string{
		"dispatch_id", "tenant_id", "project_id", "provider", "operation", "request_fingerprint",
		"status", "attempts", "fencing_token", "lease_owner_id", "lease_expires_at",
		"provider_request_id", "stream_observed", "stream_observed_sha256",
		"stream_observed_fencing_token", "stream_observed_at",
		"terminal_proof_sha256", "terminal_response_sha256",
		"reconciliation_reason", "reconciliation_attempts", "next_reconcile_at",
		"last_error_sha256", "created_at", "updated_at", "claimed_at", "completed_at", "failed_at",
	}).AddRow(dispatchID, "tenant", "project", "qwen", "chat", requestSHA, status, attempts,
		fence, owner, expiry, "", proofSHA != "", proofSHA, nullableFence(proofSHA, fence),
		nullableObservedAt(proofSHA, now), proofSHA, responseSHA, "", 0, nil, "", now, now, now,
		nil, nil)
}

func nullableFence(proofSHA string, fence int64) any {
	if proofSHA == "" {
		return nil
	}
	return fence
}

func nullableObservedAt(proofSHA string, now time.Time) any {
	if proofSHA == "" {
		return nil
	}
	return now
}

func assertProviderDispatchExpectations(t *testing.T, mock sqlmock.Sqlmock) {
	t.Helper()
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}
