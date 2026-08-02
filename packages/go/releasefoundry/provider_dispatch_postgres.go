package releasefoundry

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/lib/pq"
)

const providerDispatchTransactionAttempts = 4

const providerDispatchColumns = `
dispatch_id, tenant_id, project_id, provider, operation, request_fingerprint,
status, attempts, fencing_token, lease_owner_id, lease_expires_at,
provider_request_id, stream_observed, stream_observed_sha256,
stream_observed_fencing_token, stream_observed_at,
terminal_proof_sha256, terminal_response_sha256,
reconciliation_reason, reconciliation_attempts, next_reconcile_at,
last_error_sha256, created_at, updated_at, claimed_at, completed_at, failed_at`

const providerDispatchColumnsFromUpdateAlias = `
d.dispatch_id, d.tenant_id, d.project_id, d.provider, d.operation, d.request_fingerprint,
d.status, d.attempts, d.fencing_token, d.lease_owner_id, d.lease_expires_at,
d.provider_request_id, d.stream_observed, d.stream_observed_sha256,
d.stream_observed_fencing_token, d.stream_observed_at,
d.terminal_proof_sha256, d.terminal_response_sha256,
d.reconciliation_reason, d.reconciliation_attempts, d.next_reconcile_at,
d.last_error_sha256, d.created_at, d.updated_at, d.claimed_at, d.completed_at, d.failed_at`

func (repository *PostgresRepository) SubmitProviderDispatch(
	tenantID, projectID, provider, operation string,
	request JSONMap, options SubmitProviderDispatchOptions,
) (Envelope[ProviderDispatch], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[ProviderDispatch]{}, err
	}
	provider, operation = strings.TrimSpace(provider), strings.TrimSpace(operation)
	if provider == "" || operation == "" {
		return Envelope[ProviderDispatch]{}, fmt.Errorf("provider and operation are required")
	}
	requestFingerprint, err := fingerprint(cloneMap(request))
	if err != nil {
		return Envelope[ProviderDispatch]{}, err
	}
	now := repository.now().UTC()
	dispatchID := strings.TrimSpace(options.DispatchID)
	if dispatchID == "" {
		dispatchID = stablePostgresTimedID("dispatch", provider+"-"+operation, now)
	}
	ctx := context.Background()
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return Envelope[ProviderDispatch]{}, mapProviderDispatchOperationalError(ctx, err)
	}
	defer rollbackUnlessCommitted(tx)
	if err := setProviderDispatchScope(ctx, tx, tenantID, projectID); err != nil {
		return Envelope[ProviderDispatch]{}, mapProviderDispatchOperationalError(ctx, err)
	}
	if err := requireProject(ctx, tx, tenantID, projectID); err != nil {
		return Envelope[ProviderDispatch]{}, err
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO releasefoundry_provider_dispatches
 (tenant_id, project_id, dispatch_id, provider, operation, request_fingerprint,
  status, created_at, updated_at)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$8)
ON CONFLICT (tenant_id, project_id, dispatch_id) DO NOTHING`,
		tenantID, projectID, dispatchID, provider, operation, requestFingerprint,
		ProviderDispatchPending, now)
	if err != nil {
		return Envelope[ProviderDispatch]{}, mapProviderDispatchOperationalError(ctx, err)
	}
	dispatch, err := selectProviderDispatchForUpdate(ctx, tx, tenantID, projectID, dispatchID)
	if err != nil {
		return Envelope[ProviderDispatch]{}, err
	}
	if dispatch.RequestFingerprint != requestFingerprint ||
		dispatch.Provider != provider || dispatch.Operation != operation {
		return Envelope[ProviderDispatch]{}, &ProviderDispatchConflictError{
			DispatchID: dispatchID, ExistingFingerprint: dispatch.RequestFingerprint,
			RequestedFingerprint: requestFingerprint,
		}
	}
	if err := tx.Commit(); err != nil {
		return Envelope[ProviderDispatch]{}, mapProviderDispatchCommitError(ctx, err)
	}
	return Envelope[ProviderDispatch]{Operation: "provider.dispatch.submit", Status: "ok", Result: dispatch}, nil
}

func (repository *PostgresRepository) GetProviderDispatch(
	tenantID, projectID, dispatchID string,
) (Envelope[ProviderDispatch], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[ProviderDispatch]{}, ErrProviderDispatchUnavailable
	}
	ctx := context.Background()
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelReadCommitted, ReadOnly: true})
	if err != nil {
		return Envelope[ProviderDispatch]{}, mapProviderDispatchOperationalError(ctx, err)
	}
	defer rollbackUnlessCommitted(tx)
	if err := setProviderDispatchScope(ctx, tx, tenantID, projectID); err != nil {
		return Envelope[ProviderDispatch]{}, mapProviderDispatchOperationalError(ctx, err)
	}
	row := tx.QueryRowContext(ctx, `
SELECT `+providerDispatchColumns+` FROM releasefoundry_provider_dispatches
WHERE tenant_id=$1 AND project_id=$2 AND dispatch_id=$3`,
		tenantID, projectID, strings.TrimSpace(dispatchID))
	dispatch, err := scanProviderDispatch(row)
	if errors.Is(err, sql.ErrNoRows) {
		return Envelope[ProviderDispatch]{}, sql.ErrNoRows
	}
	if err != nil {
		return Envelope[ProviderDispatch]{}, mapProviderDispatchOperationalError(ctx, err)
	}
	if err := tx.Commit(); err != nil {
		return Envelope[ProviderDispatch]{}, mapProviderDispatchCommitError(ctx, err)
	}
	return Envelope[ProviderDispatch]{Operation: "provider.dispatch.get", Status: "ok", Result: dispatch}, nil
}

func (repository *PostgresRepository) ClaimProviderDispatch(
	tenantID, projectID, leaseOwnerID string, options ClaimProviderDispatchOptions,
) (Envelope[ProviderDispatchClaim], error) {
	return repository.ClaimProviderDispatchContext(context.Background(), tenantID, projectID, leaseOwnerID, options)
}

func (repository *PostgresRepository) ClaimProviderDispatchContext(
	ctx context.Context, tenantID, projectID, leaseOwnerID string, options ClaimProviderDispatchOptions,
) (Envelope[ProviderDispatchClaim], error) {
	return repository.claimProviderDispatch(ctx, tenantID, projectID, leaseOwnerID,
		options.Provider, options.Operation, ProviderDispatchPending, ProviderDispatchClaimed,
		options.LeaseSeconds, false)
}

func (repository *PostgresRepository) ClaimProviderDispatchReconciliation(
	tenantID, projectID, leaseOwnerID string, options ReconcileProviderDispatchOptions,
) (Envelope[ProviderDispatchClaim], error) {
	return repository.ClaimProviderDispatchReconciliationContext(
		context.Background(), tenantID, projectID, leaseOwnerID, options,
	)
}

func (repository *PostgresRepository) ClaimProviderDispatchReconciliationContext(
	ctx context.Context, tenantID, projectID, leaseOwnerID string, options ReconcileProviderDispatchOptions,
) (Envelope[ProviderDispatchClaim], error) {
	return repository.claimProviderDispatch(ctx, tenantID, projectID, leaseOwnerID,
		"", "", ProviderDispatchIndeterminate, ProviderDispatchReconciling,
		options.LeaseSeconds, true)
}

func (repository *PostgresRepository) claimProviderDispatch(
	ctx context.Context, tenantID, projectID, leaseOwnerID, provider, operation, sourceStatus, claimedStatus string,
	leaseSeconds int, reconciliation bool,
) (Envelope[ProviderDispatchClaim], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[ProviderDispatchClaim]{}, err
	}
	leaseOwnerID = strings.TrimSpace(leaseOwnerID)
	if leaseOwnerID == "" {
		return Envelope[ProviderDispatchClaim]{}, fmt.Errorf("lease_owner_id is required")
	}
	if leaseSeconds == 0 {
		leaseSeconds = 300
	}
	if leaseSeconds < 1 {
		return Envelope[ProviderDispatchClaim]{}, fmt.Errorf("lease_seconds must be positive")
	}
	if ctx == nil {
		ctx = context.Background()
	}
	for attempt := 0; attempt < providerDispatchTransactionAttempts; attempt++ {
		if err := ctx.Err(); err != nil {
			return Envelope[ProviderDispatchClaim]{}, mapProviderDispatchOperationalError(ctx, err)
		}
		now := repository.now().UTC()
		expiresAt := now.Add(time.Duration(leaseSeconds) * time.Second)
		tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
		if err != nil {
			return Envelope[ProviderDispatchClaim]{}, mapProviderDispatchOperationalError(ctx, err)
		}
		if err := setProviderDispatchScope(ctx, tx, tenantID, projectID); err != nil {
			_ = tx.Rollback()
			if shouldRetryProviderDispatchTransaction(err) && attempt+1 < providerDispatchTransactionAttempts {
				if err := waitProviderDispatchRetry(ctx, attempt); err != nil {
					return Envelope[ProviderDispatchClaim]{}, err
				}
				continue
			}
			return Envelope[ProviderDispatchClaim]{}, mapProviderDispatchOperationalError(ctx, err)
		}
		if err := requireProject(ctx, tx, tenantID, projectID); err != nil {
			_ = tx.Rollback()
			return Envelope[ProviderDispatchClaim]{}, err
		}
		row := tx.QueryRowContext(ctx, `
WITH candidate AS (
 SELECT tenant_id, project_id, dispatch_id
 FROM releasefoundry_provider_dispatches
 WHERE tenant_id=$1 AND project_id=$2
   AND (
     (status=$3 AND ($4='' OR provider=$4) AND ($5='' OR operation=$5)
       AND (next_reconcile_at IS NULL OR next_reconcile_at <= $6))
     OR (status=$7 AND lease_expires_at <= $6)
   )
 ORDER BY COALESCE(next_reconcile_at, created_at), created_at, dispatch_id
 FOR UPDATE SKIP LOCKED
 LIMIT 1
)
UPDATE releasefoundry_provider_dispatches d
SET status=$8, attempts=attempts+1, fencing_token=fencing_token+1,
    lease_owner_id=$9, lease_expires_at=$10, claimed_at=$6, updated_at=$6,
    reconciliation_attempts=reconciliation_attempts + CASE WHEN $11 THEN 1 ELSE 0 END
FROM candidate c
WHERE d.tenant_id=c.tenant_id AND d.project_id=c.project_id AND d.dispatch_id=c.dispatch_id
RETURNING `+providerDispatchColumnsFromUpdateAlias,
			tenantID, projectID, sourceStatus, provider, operation, now, claimedStatus,
			claimedStatus, leaseOwnerID, expiresAt, reconciliation)
		dispatch, err := scanProviderDispatch(row)
		if errors.Is(err, sql.ErrNoRows) {
			if err := tx.Commit(); err != nil {
				return Envelope[ProviderDispatchClaim]{}, mapProviderDispatchCommitError(ctx, err)
			}
			result := ProviderDispatchClaim{SchemaVersion: ControlPlaneSchemaVersion, Status: "empty", Claimed: false}
			return Envelope[ProviderDispatchClaim]{Operation: "provider.dispatch.claim", Status: "ok", Result: result}, nil
		}
		if err != nil {
			_ = tx.Rollback()
			if shouldRetryProviderDispatchTransaction(err) && attempt+1 < providerDispatchTransactionAttempts {
				if err := waitProviderDispatchRetry(ctx, attempt); err != nil {
					return Envelope[ProviderDispatchClaim]{}, err
				}
				continue
			}
			return Envelope[ProviderDispatchClaim]{}, mapProviderDispatchOperationalError(ctx, err)
		}
		if err := tx.Commit(); err != nil {
			return Envelope[ProviderDispatchClaim]{}, mapProviderDispatchCommitError(ctx, err)
		}
		result := ProviderDispatchClaim{SchemaVersion: ControlPlaneSchemaVersion, Status: claimedStatus, Claimed: true, Dispatch: &dispatch}
		return Envelope[ProviderDispatchClaim]{Operation: "provider.dispatch.claim", Status: "ok", Result: result}, nil
	}
	return Envelope[ProviderDispatchClaim]{}, ErrProviderDispatchContention
}

func (repository *PostgresRepository) HeartbeatProviderDispatch(
	tenantID, projectID, dispatchID, leaseOwnerID string, fencingToken int64, leaseSeconds int,
) (Envelope[ProviderDispatch], error) {
	if leaseSeconds == 0 {
		leaseSeconds = 300
	}
	if leaseSeconds < 1 {
		return Envelope[ProviderDispatch]{}, fmt.Errorf("lease_seconds must be positive")
	}
	now := repository.now().UTC()
	return repository.mutateProviderDispatchLease(tenantID, projectID, dispatchID, leaseOwnerID,
		fencingToken, now, "heartbeat", func(ctx context.Context, tx *sql.Tx) (ProviderDispatch, error) {
			row := tx.QueryRowContext(ctx, `
UPDATE releasefoundry_provider_dispatches
SET lease_expires_at=GREATEST(lease_expires_at,$6), updated_at=$5
WHERE tenant_id=$1 AND project_id=$2 AND dispatch_id=$3
  AND lease_owner_id=$4 AND fencing_token=$7
  AND status IN ($8,$9) AND lease_expires_at>$5
RETURNING `+providerDispatchColumns,
				tenantID, projectID, dispatchID, leaseOwnerID, now,
				now.Add(time.Duration(leaseSeconds)*time.Second), fencingToken,
				ProviderDispatchClaimed, ProviderDispatchReconciling)
			return scanProviderDispatch(row)
		})
}

func (repository *PostgresRepository) ObserveProviderDispatchStream(
	tenantID, projectID, dispatchID, leaseOwnerID string, fencingToken int64,
	options ObserveProviderDispatchStreamOptions,
) (Envelope[ProviderDispatch], error) {
	streamSHA, err := nonEmptyProviderDigest("provider stream", options.Stream)
	if err != nil {
		return Envelope[ProviderDispatch]{}, err
	}
	now := repository.now().UTC()
	return repository.mutateProviderDispatchLease(tenantID, projectID, dispatchID, leaseOwnerID,
		fencingToken, now, "observe_stream", func(ctx context.Context, tx *sql.Tx) (ProviderDispatch, error) {
			row := tx.QueryRowContext(ctx, `
UPDATE releasefoundry_provider_dispatches
SET stream_observed=true, stream_observed_sha256=$6,
    stream_observed_fencing_token=$7, stream_observed_at=$5, updated_at=$5
WHERE tenant_id=$1 AND project_id=$2 AND dispatch_id=$3
  AND lease_owner_id=$4 AND fencing_token=$7
  AND status IN ($8,$9) AND lease_expires_at>$5
  AND (
    stream_observed=false
    OR (stream_observed_sha256=$6 AND stream_observed_fencing_token=$7)
  )
RETURNING `+providerDispatchColumns,
				tenantID, projectID, dispatchID, leaseOwnerID, now, streamSHA, fencingToken,
				ProviderDispatchClaimed, ProviderDispatchReconciling)
			return scanProviderDispatch(row)
		})
}

func (repository *PostgresRepository) CompleteProviderDispatch(
	tenantID, projectID, dispatchID, leaseOwnerID string, fencingToken int64,
	options CompleteProviderDispatchOptions,
) (Envelope[ProviderDispatch], error) {
	proofSHA, err := nonEmptyProviderDigest("terminal proof", options.Proof)
	if err != nil {
		return Envelope[ProviderDispatch]{}, err
	}
	responseSHA, err := nonEmptyProviderDigest("terminal response", options.Response)
	if err != nil {
		return Envelope[ProviderDispatch]{}, err
	}
	now := repository.now().UTC()
	if existing, ok, err := repository.completedProviderDispatchReplay(
		tenantID, projectID, dispatchID, proofSHA, responseSHA); err != nil || ok {
		return existing, err
	}
	return repository.mutateProviderDispatchLease(tenantID, projectID, dispatchID, leaseOwnerID,
		fencingToken, now, "complete", func(ctx context.Context, tx *sql.Tx) (ProviderDispatch, error) {
			row := tx.QueryRowContext(ctx, `
UPDATE releasefoundry_provider_dispatches
SET status=$8, provider_request_id=$6, terminal_proof_sha256=$7,
    terminal_response_sha256=$10, lease_owner_id='', lease_expires_at=NULL,
    next_reconcile_at=NULL, reconciliation_reason='', completed_at=$5, updated_at=$5
WHERE tenant_id=$1 AND project_id=$2 AND dispatch_id=$3
  AND lease_owner_id=$4 AND fencing_token=$9
  AND status IN ($11,$12) AND lease_expires_at>$5
  AND stream_observed=true
  AND stream_observed_fencing_token=$9
  AND stream_observed_sha256=$7
RETURNING `+providerDispatchColumns,
				tenantID, projectID, dispatchID, leaseOwnerID, now,
				strings.TrimSpace(options.ProviderRequestID), proofSHA, ProviderDispatchCompleted,
				fencingToken, responseSHA, ProviderDispatchClaimed, ProviderDispatchReconciling)
			return scanProviderDispatch(row)
		})
}

func (repository *PostgresRepository) MarkProviderDispatchIndeterminate(
	tenantID, projectID, dispatchID, leaseOwnerID string, fencingToken int64,
	reason string, failure JSONMap, nextReconcileAt time.Time,
) (Envelope[ProviderDispatch], error) {
	reason = strings.TrimSpace(reason)
	if reason == "" {
		return Envelope[ProviderDispatch]{}, fmt.Errorf("reconciliation reason is required")
	}
	failureSHA, err := fingerprint(cloneMap(failure))
	if err != nil {
		return Envelope[ProviderDispatch]{}, err
	}
	now := repository.now().UTC()
	if nextReconcileAt.IsZero() {
		nextReconcileAt = now
	}
	return repository.mutateProviderDispatchLease(tenantID, projectID, dispatchID, leaseOwnerID,
		fencingToken, now, "indeterminate", func(ctx context.Context, tx *sql.Tx) (ProviderDispatch, error) {
			row := tx.QueryRowContext(ctx, `
UPDATE releasefoundry_provider_dispatches
SET status=$8, reconciliation_reason=$6, last_error_sha256=$7,
    next_reconcile_at=$10, lease_owner_id='', lease_expires_at=NULL, updated_at=$5
WHERE tenant_id=$1 AND project_id=$2 AND dispatch_id=$3
  AND lease_owner_id=$4 AND fencing_token=$9
  AND status IN ($11,$12) AND lease_expires_at>$5
  AND stream_observed=false
RETURNING `+providerDispatchColumns,
				tenantID, projectID, dispatchID, leaseOwnerID, now, reason, failureSHA,
				ProviderDispatchIndeterminate, fencingToken, nextReconcileAt,
				ProviderDispatchClaimed, ProviderDispatchReconciling)
			return scanProviderDispatch(row)
		})
}

func (repository *PostgresRepository) mutateProviderDispatchLease(
	tenantID, projectID, dispatchID, leaseOwnerID string, fencingToken int64,
	now time.Time, operation string,
	mutate func(context.Context, *sql.Tx) (ProviderDispatch, error),
) (Envelope[ProviderDispatch], error) {
	if err := repository.requireDB(); err != nil {
		return Envelope[ProviderDispatch]{}, err
	}
	if strings.TrimSpace(dispatchID) == "" || strings.TrimSpace(leaseOwnerID) == "" || fencingToken < 1 {
		return Envelope[ProviderDispatch]{}, &ProviderDispatchFenceError{DispatchID: dispatchID, LeaseOwnerID: leaseOwnerID, FencingToken: fencingToken}
	}
	ctx := context.Background()
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return Envelope[ProviderDispatch]{}, mapProviderDispatchOperationalError(ctx, err)
	}
	defer rollbackUnlessCommitted(tx)
	if err := setProviderDispatchScope(ctx, tx, tenantID, projectID); err != nil {
		return Envelope[ProviderDispatch]{}, mapProviderDispatchOperationalError(ctx, err)
	}
	if err := requireProject(ctx, tx, tenantID, projectID); err != nil {
		return Envelope[ProviderDispatch]{}, err
	}
	dispatch, err := mutate(ctx, tx)
	if errors.Is(err, sql.ErrNoRows) {
		return Envelope[ProviderDispatch]{}, &ProviderDispatchFenceError{DispatchID: dispatchID, LeaseOwnerID: leaseOwnerID, FencingToken: fencingToken}
	}
	if err != nil {
		return Envelope[ProviderDispatch]{}, mapProviderDispatchOperationalError(ctx, err)
	}
	if err := tx.Commit(); err != nil {
		return Envelope[ProviderDispatch]{}, mapProviderDispatchCommitError(ctx, err)
	}
	return Envelope[ProviderDispatch]{Operation: "provider.dispatch." + operation, Status: "ok", Result: dispatch}, nil
}

func (repository *PostgresRepository) completedProviderDispatchReplay(
	tenantID, projectID, dispatchID, proofSHA, responseSHA string,
) (Envelope[ProviderDispatch], bool, error) {
	ctx := context.Background()
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelReadCommitted, ReadOnly: true})
	if err != nil {
		return Envelope[ProviderDispatch]{}, false, mapProviderDispatchOperationalError(ctx, err)
	}
	defer rollbackUnlessCommitted(tx)
	if err := setProviderDispatchScope(ctx, tx, tenantID, projectID); err != nil {
		return Envelope[ProviderDispatch]{}, false, mapProviderDispatchOperationalError(ctx, err)
	}
	if err := requireProject(ctx, tx, tenantID, projectID); err != nil {
		return Envelope[ProviderDispatch]{}, false, err
	}
	row := tx.QueryRowContext(ctx, `
SELECT `+providerDispatchColumns+` FROM releasefoundry_provider_dispatches
WHERE tenant_id=$1 AND project_id=$2 AND dispatch_id=$3`, tenantID, projectID, dispatchID)
	dispatch, err := scanProviderDispatch(row)
	if errors.Is(err, sql.ErrNoRows) {
		if err := tx.Commit(); err != nil {
			return Envelope[ProviderDispatch]{}, false, mapProviderDispatchCommitError(ctx, err)
		}
		return Envelope[ProviderDispatch]{}, false, nil
	}
	if err != nil {
		return Envelope[ProviderDispatch]{}, false, mapProviderDispatchOperationalError(ctx, err)
	}
	if dispatch.Status != ProviderDispatchCompleted {
		if err := tx.Commit(); err != nil {
			return Envelope[ProviderDispatch]{}, false, mapProviderDispatchCommitError(ctx, err)
		}
		return Envelope[ProviderDispatch]{}, false, nil
	}
	if dispatch.TerminalProofSHA256 != proofSHA || dispatch.TerminalResponseSHA256 != responseSHA {
		return Envelope[ProviderDispatch]{}, true, &ProviderDispatchConflictError{
			DispatchID: dispatchID, ExistingFingerprint: dispatch.TerminalProofSHA256,
			RequestedFingerprint: proofSHA,
		}
	}
	if err := tx.Commit(); err != nil {
		return Envelope[ProviderDispatch]{}, false, mapProviderDispatchCommitError(ctx, err)
	}
	return Envelope[ProviderDispatch]{Operation: "provider.dispatch.complete", Status: "ok", Result: dispatch}, true, nil
}

func setProviderDispatchScope(ctx context.Context, tx *sql.Tx, tenantID, projectID string) error {
	_, err := tx.ExecContext(ctx, `
SELECT set_config('app.a1_organization_id', $1, true),
       set_config('app.a1_project_id', $2, true)
`, tenantID, projectID)
	return err
}

func shouldRetryProviderDispatchTransaction(err error) bool {
	var postgresError *pq.Error
	return errors.As(err, &postgresError) &&
		(postgresError.Code == "40001" || postgresError.Code == "40P01")
}

func waitProviderDispatchRetry(ctx context.Context, attempt int) error {
	delay := time.Duration(attempt+1) * 10 * time.Millisecond
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return mapProviderDispatchOperationalError(ctx, ctx.Err())
	case <-timer.C:
		return nil
	}
}

func mapProviderDispatchCommitError(ctx context.Context, err error) error {
	if ctx != nil && ctx.Err() != nil {
		return mapProviderDispatchOperationalError(ctx, ctx.Err())
	}
	// A failed commit can be ambiguous; never replay the transaction automatically.
	return ErrProviderDispatchIndeterminate
}

func mapProviderDispatchOperationalError(ctx context.Context, err error) error {
	if errors.Is(err, context.Canceled) || (ctx != nil && errors.Is(ctx.Err(), context.Canceled)) {
		return ErrProviderDispatchCancelled
	}
	if errors.Is(err, context.DeadlineExceeded) || (ctx != nil && errors.Is(ctx.Err(), context.DeadlineExceeded)) {
		return ErrProviderDispatchDeadline
	}
	if shouldRetryProviderDispatchTransaction(err) {
		return ErrProviderDispatchContention
	}
	if errors.Is(err, sql.ErrConnDone) || errors.Is(err, sql.ErrTxDone) {
		return ErrProviderDispatchUnavailable
	}
	return ErrProviderDispatchUnavailable
}

func nonEmptyProviderDigest(name string, value JSONMap) (string, error) {
	if len(value) == 0 {
		return "", fmt.Errorf("%s is required", name)
	}
	digest, err := fingerprint(cloneMap(value))
	if err != nil {
		return "", err
	}
	return digest, nil
}

func selectProviderDispatchForUpdate(
	ctx context.Context, tx *sql.Tx, tenantID, projectID, dispatchID string,
) (ProviderDispatch, error) {
	row := tx.QueryRowContext(ctx, `
SELECT `+providerDispatchColumns+`
FROM releasefoundry_provider_dispatches
WHERE tenant_id=$1 AND project_id=$2 AND dispatch_id=$3
FOR UPDATE`, tenantID, projectID, dispatchID)
	dispatch, err := scanProviderDispatch(row)
	if errors.Is(err, sql.ErrNoRows) {
		return ProviderDispatch{}, fmt.Errorf("provider dispatch %q was not found after insert", dispatchID)
	}
	if err != nil {
		return ProviderDispatch{}, mapProviderDispatchOperationalError(ctx, err)
	}
	return dispatch, nil
}

type providerDispatchScanner interface {
	Scan(dest ...any) error
}

func scanProviderDispatch(scanner providerDispatchScanner) (ProviderDispatch, error) {
	var dispatch ProviderDispatch
	var leaseExpiresAt, streamObservedAt, nextReconcileAt, claimedAt, completedAt, failedAt sql.NullTime
	var streamObservedFence sql.NullInt64
	err := scanner.Scan(
		&dispatch.DispatchID, &dispatch.TenantID, &dispatch.ProjectID, &dispatch.Provider,
		&dispatch.Operation, &dispatch.RequestFingerprint, &dispatch.Status, &dispatch.Attempts,
		&dispatch.FencingToken, &dispatch.LeaseOwnerID, &leaseExpiresAt,
		&dispatch.ProviderRequestID, &dispatch.StreamObserved, &dispatch.StreamObservedSHA256,
		&streamObservedFence, &streamObservedAt,
		&dispatch.TerminalProofSHA256, &dispatch.TerminalResponseSHA256,
		&dispatch.ReconciliationReason, &dispatch.ReconciliationAttempts, &nextReconcileAt,
		&dispatch.LastErrorSHA256, &dispatch.CreatedAt, &dispatch.UpdatedAt, &claimedAt,
		&completedAt, &failedAt,
	)
	if err != nil {
		return ProviderDispatch{}, err
	}
	dispatch.SchemaVersion = ControlPlaneSchemaVersion
	dispatch.RawPayloadIncluded = false
	dispatch.LeaseExpiresAt = nullableTime(leaseExpiresAt)
	dispatch.StreamObservedFence = nullableInt64(streamObservedFence)
	dispatch.StreamObservedAt = nullableTime(streamObservedAt)
	dispatch.NextReconcileAt = nullableTime(nextReconcileAt)
	dispatch.ClaimedAt = nullableTime(claimedAt)
	dispatch.CompletedAt = nullableTime(completedAt)
	dispatch.FailedAt = nullableTime(failedAt)
	return dispatch, nil
}

func nullableInt64(value sql.NullInt64) *int64 {
	if !value.Valid {
		return nil
	}
	result := value.Int64
	return &result
}

func nullableTime(value sql.NullTime) *time.Time {
	if !value.Valid {
		return nil
	}
	result := value.Time
	return &result
}
