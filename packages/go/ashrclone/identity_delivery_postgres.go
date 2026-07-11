package ashrclone

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"
)

const (
	postgresIdentityDeliveryLeaseLostSQLState     = "P0001"
	postgresIdentityDeliveryLeaseExpiredSQLState  = "P0002"
	postgresIdentityDeliveryChallengeExpiredState = "P0003"
	postgresIdentityDeliverySerializationSQLState = "40001"
	postgresIdentityDeliveryInsufficientPrivilege = "42501"
	minPostgresIdentityDeliveryLease              = 100 * time.Millisecond
	maxPostgresIdentityDeliveryLease              = time.Hour
)

var postgresIdentityDeliveryProviderKeyPattern = regexp.MustCompile(
	`^[A-Za-z0-9][A-Za-z0-9._:-]{7,255}$`,
)

// PostgresIdentityDeliveryOutboxStore uses only the scoped SECURITY DEFINER
// functions installed by migration 014. The runtime role needs no direct
// access to either the outbox or redrive audit table.
type PostgresIdentityDeliveryOutboxStore struct {
	db *sql.DB
}

func NewPostgresIdentityDeliveryOutboxStore(
	db *sql.DB,
) (*PostgresIdentityDeliveryOutboxStore, error) {
	if db == nil {
		return nil, fmt.Errorf("PostgreSQL identity delivery db is required")
	}
	return &PostgresIdentityDeliveryOutboxStore{db: db}, nil
}

func (store *PostgresIdentityDeliveryOutboxStore) ClaimIdentityDeliveries(
	ctx context.Context,
	tenantID string,
	projectID string,
	leaseOwner string,
	limit int,
	leaseDuration time.Duration,
	now time.Time,
) ([]IdentityDeliveryTask, error) {
	if err := validatePostgresIdentityDeliveryScope(tenantID, projectID); err != nil {
		return nil, err
	}
	if !validIdentityDeliveryIdentifier(leaseOwner) {
		return nil, fmt.Errorf("PostgreSQL identity delivery lease owner is invalid")
	}
	if limit < 1 || limit > 500 {
		return nil, fmt.Errorf("PostgreSQL identity delivery claim limit must be between 1 and 500")
	}
	leaseMilliseconds, err := postgresIdentityDeliveryLeaseMilliseconds(leaseDuration)
	if err != nil {
		return nil, err
	}
	now = postgresIdentityDeliveryNow(now)

	tx, err := store.beginScopedTransaction(ctx, tenantID, projectID)
	if err != nil {
		return nil, err
	}
	defer rollbackUnlessCommitted(tx)

	rows, err := tx.QueryContext(ctx, `
SELECT outbox_id::text,
       organization_id::text,
       project_id::text,
       challenge_id::text,
       channel,
       purpose,
       opaque_ref,
       challenge_expires_at,
       attempt_count,
       max_attempts,
       provider_idempotency_key,
       lease_owner,
       lease_generation,
       lease_expires_at
  FROM a1_claim_identity_delivery_outbox(
    $1::uuid, $2::uuid, $3, $4, $5, $6
  )
`, tenantID, projectID, leaseOwner, limit, leaseMilliseconds, now)
	if err != nil {
		return nil, mapPostgresIdentityDeliveryError("claim", err)
	}

	tasks := make([]IdentityDeliveryTask, 0, limit)
	for rows.Next() {
		var task IdentityDeliveryTask
		var rowTenantID, rowProjectID, channel, purpose string
		var providerIdempotencyKey string
		if err := rows.Scan(
			&task.ID,
			&rowTenantID,
			&rowProjectID,
			&task.ChallengeID,
			&channel,
			&purpose,
			&task.OpaqueRef,
			&task.ChallengeExpiresAt,
			&task.Attempt,
			&task.MaxAttempts,
			&providerIdempotencyKey,
			&task.LeaseOwner,
			&task.LeaseGeneration,
			&task.LeaseExpiresAt,
		); err != nil {
			_ = rows.Close()
			return nil, fmt.Errorf("scan PostgreSQL identity delivery claim: %w", err)
		}
		task.TenantID = rowTenantID
		task.ProjectID = rowProjectID
		task.Channel = IdentityVerificationChannel(channel)
		task.Purpose = postgresIdentityDeliveryPurpose(purpose)
		task.ProviderIdempotencyKey = providerIdempotencyKey
		if rowTenantID != tenantID || rowProjectID != projectID {
			_ = rows.Close()
			return nil, fmt.Errorf("%w: claimed PostgreSQL identity delivery crossed scope", ErrIdentityDeliveryScope)
		}
		if !postgresIdentityDeliveryProviderKeyPattern.MatchString(providerIdempotencyKey) {
			_ = rows.Close()
			return nil, fmt.Errorf("PostgreSQL identity delivery provider idempotency key is invalid")
		}
		if err := validatePostgresIdentityDeliveryClaim(task, leaseOwner, now); err != nil {
			_ = rows.Close()
			return nil, err
		}
		tasks = append(tasks, task)
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return nil, fmt.Errorf("iterate PostgreSQL identity delivery claims: %w", err)
	}
	if err := rows.Close(); err != nil {
		return nil, fmt.Errorf("close PostgreSQL identity delivery claims: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("commit PostgreSQL identity delivery claim: %w", err)
	}
	return tasks, nil
}

func (store *PostgresIdentityDeliveryOutboxStore) HeartbeatIdentityDelivery(
	ctx context.Context,
	task IdentityDeliveryTask,
	leaseDuration time.Duration,
	now time.Time,
) (IdentityDeliveryTask, error) {
	now = postgresIdentityDeliveryNow(now)
	if err := validatePostgresIdentityDeliveryFence(task, now); err != nil {
		return IdentityDeliveryTask{}, err
	}
	leaseMilliseconds, err := postgresIdentityDeliveryLeaseMilliseconds(leaseDuration)
	if err != nil {
		return IdentityDeliveryTask{}, err
	}

	tx, err := store.beginScopedTransaction(ctx, task.TenantID, task.ProjectID)
	if err != nil {
		return IdentityDeliveryTask{}, err
	}
	defer rollbackUnlessCommitted(tx)

	var leaseExpiresAt time.Time
	err = tx.QueryRowContext(ctx, `
SELECT a1_heartbeat_identity_delivery_outbox(
  $1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7
)
`, task.TenantID, task.ProjectID, task.ID, task.LeaseOwner,
		task.LeaseGeneration, leaseMilliseconds, now).Scan(&leaseExpiresAt)
	if err != nil {
		return IdentityDeliveryTask{}, mapPostgresIdentityDeliveryError("heartbeat", err)
	}
	leaseExpiresAt = leaseExpiresAt.UTC()
	if leaseExpiresAt.Before(task.LeaseExpiresAt) || !leaseExpiresAt.After(now) {
		return IdentityDeliveryTask{}, fmt.Errorf(
			"%w: PostgreSQL identity delivery heartbeat returned an invalid lease",
			ErrIdentityDeliveryLeaseLost,
		)
	}
	if err := tx.Commit(); err != nil {
		return IdentityDeliveryTask{}, fmt.Errorf("commit PostgreSQL identity delivery heartbeat: %w", err)
	}
	task.LeaseExpiresAt = leaseExpiresAt
	return task, nil
}

func (store *PostgresIdentityDeliveryOutboxStore) CompleteIdentityDelivery(
	ctx context.Context,
	task IdentityDeliveryTask,
	acceptance IdentityDeliveryProviderAcceptance,
	now time.Time,
) error {
	now = postgresIdentityDeliveryNow(now)
	if err := validatePostgresIdentityDeliveryFence(task, now); err != nil {
		return err
	}
	if err := validateIdentityDeliveryProviderAcceptance(task, acceptance, now); err != nil {
		return err
	}

	tx, err := store.beginScopedTransaction(ctx, task.TenantID, task.ProjectID)
	if err != nil {
		return err
	}
	defer rollbackUnlessCommitted(tx)

	var outboxID string
	err = tx.QueryRowContext(ctx, `
SELECT a1_complete_identity_delivery_outbox(
  p_organization_id => $1::uuid,
  p_project_id => $2::uuid,
  p_outbox_id => $3::uuid,
  p_lease_owner => $4,
  p_lease_generation => $5,
  p_provider_acceptance_ref => $6,
  p_provider_accepted_at => $7,
  p_now => $8
)::text
`, task.TenantID, task.ProjectID, task.ID, task.LeaseOwner,
		task.LeaseGeneration, acceptance.Reference, acceptance.AcceptedAt.UTC(), now,
	).Scan(&outboxID)
	if err != nil {
		return mapPostgresIdentityDeliveryError("complete", err)
	}
	if outboxID != task.ID {
		return fmt.Errorf("%w: PostgreSQL identity delivery complete returned another task", ErrIdentityDeliveryLeaseLost)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit PostgreSQL identity delivery complete: %w", err)
	}
	return nil
}

func (store *PostgresIdentityDeliveryOutboxStore) RetryIdentityDelivery(
	ctx context.Context,
	task IdentityDeliveryTask,
	errorCode string,
	availableAt time.Time,
	now time.Time,
) error {
	now = postgresIdentityDeliveryNow(now)
	if err := validatePostgresIdentityDeliveryFence(task, now); err != nil {
		return err
	}
	errorCode, err := normalizePostgresIdentityDeliveryErrorCode(errorCode)
	if err != nil {
		return err
	}
	availableAt = availableAt.UTC()
	if availableAt.Before(now) || availableAt.After(now.Add(24*time.Hour)) {
		return fmt.Errorf("PostgreSQL identity delivery retry time is invalid")
	}

	tx, err := store.beginScopedTransaction(ctx, task.TenantID, task.ProjectID)
	if err != nil {
		return err
	}
	defer rollbackUnlessCommitted(tx)

	var outboxID string
	err = tx.QueryRowContext(ctx, `
SELECT a1_retry_identity_delivery_outbox(
  $1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8
)::text
`, task.TenantID, task.ProjectID, task.ID, task.LeaseOwner,
		task.LeaseGeneration, errorCode, availableAt, now).Scan(&outboxID)
	if err != nil {
		return mapPostgresIdentityDeliveryError("retry", err)
	}
	if outboxID != task.ID {
		return fmt.Errorf("%w: PostgreSQL identity delivery retry returned another task", ErrIdentityDeliveryLeaseLost)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit PostgreSQL identity delivery retry: %w", err)
	}
	return nil
}

func (store *PostgresIdentityDeliveryOutboxStore) DeadLetterIdentityDelivery(
	ctx context.Context,
	task IdentityDeliveryTask,
	errorCode string,
	now time.Time,
) error {
	now = postgresIdentityDeliveryNow(now)
	if err := validatePostgresIdentityDeliveryFence(task, now); err != nil {
		return err
	}
	errorCode, err := normalizePostgresIdentityDeliveryErrorCode(errorCode)
	if err != nil {
		return err
	}

	tx, err := store.beginScopedTransaction(ctx, task.TenantID, task.ProjectID)
	if err != nil {
		return err
	}
	defer rollbackUnlessCommitted(tx)

	var outboxID string
	err = tx.QueryRowContext(ctx, `
SELECT a1_dead_letter_identity_delivery_outbox(
  $1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7
)::text
`, task.TenantID, task.ProjectID, task.ID, task.LeaseOwner,
		task.LeaseGeneration, errorCode, now).Scan(&outboxID)
	if err != nil {
		return mapPostgresIdentityDeliveryError("dead-letter", err)
	}
	if outboxID != task.ID {
		return fmt.Errorf("%w: PostgreSQL identity delivery dead-letter returned another task", ErrIdentityDeliveryLeaseLost)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit PostgreSQL identity delivery dead-letter: %w", err)
	}
	return nil
}

func (store *PostgresIdentityDeliveryOutboxStore) RedriveIdentityDelivery(
	ctx context.Context,
	command IdentityDeliveryRedriveCommand,
) (IdentityDeliveryRedriveReceipt, error) {
	if err := validateIdentityDeliveryRedriveRequest(command.IdentityDeliveryRedriveRequest); err != nil {
		return IdentityDeliveryRedriveReceipt{}, err
	}
	if err := validatePostgresIdentityDeliveryScope(command.TenantID, command.ProjectID); err != nil {
		return IdentityDeliveryRedriveReceipt{}, err
	}
	if !validPostgresIdentityVerificationUUID(command.TaskID) {
		return IdentityDeliveryRedriveReceipt{}, fmt.Errorf("PostgreSQL identity delivery task id must be a canonical UUID")
	}
	if command.RequestedAt.IsZero() {
		return IdentityDeliveryRedriveReceipt{}, fmt.Errorf("PostgreSQL identity delivery redrive time is required")
	}
	command.RequestedAt = command.RequestedAt.UTC()

	tx, err := store.beginScopedTransaction(ctx, command.TenantID, command.ProjectID)
	if err != nil {
		return IdentityDeliveryRedriveReceipt{}, err
	}
	defer rollbackUnlessCommitted(tx)

	var receipt IdentityDeliveryRedriveReceipt
	err = tx.QueryRowContext(ctx, `
SELECT outbox_id::text, lease_generation, audit_id::text, redriven_at
  FROM a1_redrive_identity_delivery_outbox(
    $1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8
  )
`, command.TenantID, command.ProjectID, command.TaskID,
		command.ExpectedLeaseGeneration, command.ActorID, command.ReasonCode,
		command.RequestID, command.RequestedAt).Scan(
		&receipt.TaskID,
		&receipt.LeaseGeneration,
		&receipt.AuditID,
		&receipt.RedrivenAt,
	)
	if err != nil {
		return IdentityDeliveryRedriveReceipt{}, mapPostgresIdentityDeliveryError("redrive", err)
	}
	receipt.RedrivenAt = receipt.RedrivenAt.UTC()
	if receipt.TaskID != command.TaskID ||
		receipt.LeaseGeneration <= command.ExpectedLeaseGeneration ||
		!validPostgresIdentityVerificationUUID(receipt.AuditID) ||
		receipt.RedrivenAt.IsZero() {
		return IdentityDeliveryRedriveReceipt{}, fmt.Errorf("PostgreSQL identity delivery redrive receipt is invalid")
	}
	if err := tx.Commit(); err != nil {
		return IdentityDeliveryRedriveReceipt{}, fmt.Errorf("commit PostgreSQL identity delivery redrive: %w", err)
	}
	return receipt, nil
}

func (store *PostgresIdentityDeliveryOutboxStore) execIdentityDeliveryTransition(
	ctx context.Context,
	task IdentityDeliveryTask,
	now time.Time,
	operation string,
	statement string,
) error {
	if err := validatePostgresIdentityDeliveryFence(task, now); err != nil {
		return err
	}
	tx, err := store.beginScopedTransaction(ctx, task.TenantID, task.ProjectID)
	if err != nil {
		return err
	}
	defer rollbackUnlessCommitted(tx)

	var outboxID string
	err = tx.QueryRowContext(
		ctx,
		statement,
		task.TenantID,
		task.ProjectID,
		task.ID,
		task.LeaseOwner,
		task.LeaseGeneration,
		now,
	).Scan(&outboxID)
	if err != nil {
		return mapPostgresIdentityDeliveryError(operation, err)
	}
	if outboxID != task.ID {
		return fmt.Errorf("%w: PostgreSQL identity delivery %s returned another task", ErrIdentityDeliveryLeaseLost, operation)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit PostgreSQL identity delivery %s: %w", operation, err)
	}
	return nil
}

func (store *PostgresIdentityDeliveryOutboxStore) beginScopedTransaction(
	ctx context.Context,
	tenantID string,
	projectID string,
) (*sql.Tx, error) {
	if store == nil || store.db == nil {
		return nil, fmt.Errorf("PostgreSQL identity delivery store is unavailable")
	}
	if ctx == nil {
		return nil, fmt.Errorf("PostgreSQL identity delivery context is required")
	}
	tx, err := store.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return nil, fmt.Errorf("begin PostgreSQL identity delivery transaction: %w", err)
	}
	if err := setPostgresIdentityVerificationScope(ctx, tx, tenantID, projectID); err != nil {
		_ = tx.Rollback()
		return nil, mapPostgresIdentityDeliveryError("set scope", err)
	}
	return tx, nil
}

func validatePostgresIdentityDeliveryScope(tenantID, projectID string) error {
	if !validPostgresIdentityVerificationUUID(tenantID) ||
		!validPostgresIdentityVerificationUUID(projectID) {
		return fmt.Errorf("%w: PostgreSQL identity delivery scope must use canonical UUIDs", ErrIdentityDeliveryScope)
	}
	return nil
}

func validatePostgresIdentityDeliveryFence(
	task IdentityDeliveryTask,
	now time.Time,
) error {
	if err := validatePostgresIdentityDeliveryScope(task.TenantID, task.ProjectID); err != nil {
		return err
	}
	if !validPostgresIdentityVerificationUUID(task.ID) ||
		!validPostgresIdentityVerificationUUID(task.ChallengeID) {
		return fmt.Errorf("%w: PostgreSQL identity delivery fence ids are invalid", ErrIdentityDeliveryLeaseLost)
	}
	return validateIdentityDeliveryFence(task, now)
}

func validatePostgresIdentityDeliveryClaim(
	task IdentityDeliveryTask,
	leaseOwner string,
	now time.Time,
) error {
	if err := validatePostgresIdentityDeliveryFence(task, now); err != nil {
		return err
	}
	if task.LeaseOwner != leaseOwner {
		return fmt.Errorf("%w: PostgreSQL identity delivery owner changed", ErrIdentityDeliveryLeaseLost)
	}
	if err := validateIdentityDeliveryTask(task); err != nil {
		return fmt.Errorf("invalid PostgreSQL identity delivery claim: %w", err)
	}
	if task.MaxAttempts < task.Attempt {
		return fmt.Errorf("invalid PostgreSQL identity delivery attempt fence")
	}
	return nil
}

func postgresIdentityDeliveryLeaseMilliseconds(lease time.Duration) (int64, error) {
	if lease < minPostgresIdentityDeliveryLease || lease > maxPostgresIdentityDeliveryLease {
		return 0, fmt.Errorf("PostgreSQL identity delivery lease must be between 100ms and 1h")
	}
	milliseconds := lease.Milliseconds()
	if milliseconds < minPostgresIdentityDeliveryLease.Milliseconds() ||
		milliseconds > maxPostgresIdentityDeliveryLease.Milliseconds() {
		return 0, fmt.Errorf("PostgreSQL identity delivery lease precision is invalid")
	}
	return milliseconds, nil
}

func postgresIdentityDeliveryNow(now time.Time) time.Time {
	if now.IsZero() {
		return time.Now().UTC()
	}
	return now.UTC()
}

func postgresIdentityDeliveryPurpose(value string) IdentityVerificationPurpose {
	switch value {
	case "credential_binding":
		return IdentityVerificationBinding
	case "account_recovery":
		return IdentityVerificationRecovery
	default:
		return IdentityVerificationPurpose(value)
	}
}

func normalizePostgresIdentityDeliveryErrorCode(value string) (string, error) {
	value = strings.ToLower(strings.TrimSpace(value))
	if !identityDeliveryReasonPattern.MatchString(value) {
		return "", fmt.Errorf("PostgreSQL identity delivery error code is invalid")
	}
	return value, nil
}

func mapPostgresIdentityDeliveryError(operation string, err error) error {
	if err == nil {
		return nil
	}
	if errors.Is(err, sql.ErrNoRows) {
		return fmt.Errorf("PostgreSQL identity delivery lease lost during %s: %w", operation, ErrIdentityDeliveryLeaseLost)
	}
	var sqlState interface{ SQLState() string }
	if errors.As(err, &sqlState) {
		switch sqlState.SQLState() {
		case postgresIdentityDeliveryLeaseExpiredSQLState,
			postgresIdentityDeliveryChallengeExpiredState:
			return fmt.Errorf("PostgreSQL identity delivery expired during %s: %w", operation, ErrIdentityDeliveryLeaseExpired)
		case postgresIdentityDeliveryLeaseLostSQLState,
			postgresIdentityDeliverySerializationSQLState:
			return fmt.Errorf("PostgreSQL identity delivery lease lost during %s: %w", operation, ErrIdentityDeliveryLeaseLost)
		case postgresIdentityDeliveryInsufficientPrivilege:
			return fmt.Errorf("PostgreSQL identity delivery scope rejected during %s: %w", operation, ErrIdentityDeliveryScope)
		}
	}
	return fmt.Errorf("PostgreSQL identity delivery %s failed: %w", operation, err)
}

var _ IdentityDeliveryOutboxStore = (*PostgresIdentityDeliveryOutboxStore)(nil)
