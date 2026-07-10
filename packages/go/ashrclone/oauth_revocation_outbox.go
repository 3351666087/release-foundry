package ashrclone

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"math"
	"regexp"
	"strings"
	"time"
)

var oauthRevocationErrorCodePattern = regexp.MustCompile(`^[a-z][a-z0-9_.-]{1,63}$`)

// OAuthRevocationTask is a fenced lease for one provider-token cleanup.
// OpaqueRef is a vault reference, never provider token material.
type OAuthRevocationTask struct {
	ID                string
	TenantID          string
	ProjectID         string
	Provider          string
	ConnectionID      string
	TokenRefID        string
	OpaqueRef         string
	OperationKind     string
	ReasonCode        string
	Attempt           int
	MaxAttempts       int
	LeaseOwner        string
	LeaseGeneration   int64
	LeaseExpiresAt    time.Time
	ProviderRevokedAt *time.Time
	VaultDeletedAt    *time.Time
}

type OAuthRevocationOutboxStore interface {
	ClaimOAuthRevocations(
		context.Context,
		string,
		string,
		string,
		int,
		time.Duration,
		time.Time,
	) ([]OAuthRevocationTask, error)
	MarkOAuthProviderRevoked(context.Context, OAuthRevocationTask, time.Time) error
	MarkOAuthVaultDeleted(context.Context, OAuthRevocationTask, time.Time) error
	CompleteOAuthRevocation(context.Context, OAuthRevocationTask, time.Time) error
	RetryOAuthRevocation(
		context.Context,
		OAuthRevocationTask,
		string,
		time.Duration,
		time.Duration,
		time.Time,
	) (bool, time.Time, error)
}

type PostgresOAuthRevocationOutboxStore struct {
	db *sql.DB
}

func NewPostgresOAuthRevocationOutboxStore(db *sql.DB) (*PostgresOAuthRevocationOutboxStore, error) {
	if db == nil {
		return nil, fmt.Errorf("OAuth revocation outbox db is required")
	}
	return &PostgresOAuthRevocationOutboxStore{db: db}, nil
}

func (store *PostgresOAuthRevocationOutboxStore) ClaimOAuthRevocations(
	ctx context.Context,
	tenantID string,
	projectID string,
	leaseOwner string,
	limit int,
	leaseDuration time.Duration,
	now time.Time,
) ([]OAuthRevocationTask, error) {
	if strings.TrimSpace(leaseOwner) == "" {
		return nil, fmt.Errorf("OAuth revocation lease owner is required")
	}
	if limit < 1 || limit > 500 {
		return nil, fmt.Errorf("OAuth revocation claim limit must be between 1 and 500")
	}
	leaseSeconds := int(leaseDuration / time.Second)
	if leaseSeconds < 5 || leaseSeconds > 3600 {
		return nil, fmt.Errorf("OAuth revocation lease must be between 5 seconds and 1 hour")
	}
	if now.IsZero() {
		now = time.Now().UTC()
	}
	organizationID, scopedProjectID := postgresOAuthScope(tenantID, projectID)
	tx, err := store.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, fmt.Errorf("begin OAuth revocation claim: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	if err := setPostgresOAuthScopeNeutral(ctx, tx, organizationID, scopedProjectID); err != nil {
		return nil, err
	}
	rows, err := tx.QueryContext(ctx, `
SELECT outbox_id, organization_id, project_id, provider, connection_id,
       token_ref_id, opaque_ref, operation_kind, reason_code, attempts,
       max_attempts, lease_owner, lease_generation, lease_expires_at,
       provider_revoked_at, vault_deleted_at
  FROM a1_claim_identity_revocation_outbox(
    $1::uuid, $2::uuid, $3, $4, $5, $6
  )
`, organizationID, scopedProjectID, leaseOwner, limit, leaseSeconds, now.UTC())
	if err != nil {
		return nil, fmt.Errorf("claim OAuth revocation outbox: %w", err)
	}
	defer rows.Close()
	tasks := make([]OAuthRevocationTask, 0, limit)
	for rows.Next() {
		var task OAuthRevocationTask
		var rowOrganizationID string
		var rowProjectID string
		if err := rows.Scan(
			&task.ID, &rowOrganizationID, &rowProjectID, &task.Provider,
			&task.ConnectionID, &task.TokenRefID, &task.OpaqueRef,
			&task.OperationKind, &task.ReasonCode, &task.Attempt,
			&task.MaxAttempts, &task.LeaseOwner, &task.LeaseGeneration,
			&task.LeaseExpiresAt, &task.ProviderRevokedAt, &task.VaultDeletedAt,
		); err != nil {
			return nil, fmt.Errorf("scan OAuth revocation lease: %w", err)
		}
		if !isOAuthOpaqueReference(task.OpaqueRef) {
			return nil, fmt.Errorf("OAuth revocation lease contains an invalid opaque reference")
		}
		task.TenantID = tenantID
		task.ProjectID = projectID
		tasks = append(tasks, task)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate OAuth revocation leases: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("commit OAuth revocation claim: %w", err)
	}
	return tasks, nil
}

func (store *PostgresOAuthRevocationOutboxStore) MarkOAuthProviderRevoked(
	ctx context.Context,
	task OAuthRevocationTask,
	now time.Time,
) error {
	if err := validateOAuthRevocationLease(task); err != nil {
		return err
	}
	if now.IsZero() {
		now = time.Now().UTC()
	}
	return store.execLeaseTransition(
		ctx,
		task,
		"SELECT a1_mark_identity_revocation_provider_revoked($1::uuid, $2::uuid, $3::uuid, $4, $5, $6)",
		"mark provider revoked",
		now.UTC(),
	)
}

func (store *PostgresOAuthRevocationOutboxStore) MarkOAuthVaultDeleted(
	ctx context.Context,
	task OAuthRevocationTask,
	now time.Time,
) error {
	if err := validateOAuthRevocationLease(task); err != nil {
		return err
	}
	if now.IsZero() {
		now = time.Now().UTC()
	}
	return store.execLeaseTransition(
		ctx,
		task,
		"SELECT a1_mark_identity_revocation_vault_deleted($1::uuid, $2::uuid, $3::uuid, $4, $5, $6)",
		"mark vault deleted",
		now.UTC(),
	)
}

func (store *PostgresOAuthRevocationOutboxStore) CompleteOAuthRevocation(
	ctx context.Context,
	task OAuthRevocationTask,
	now time.Time,
) error {
	if err := validateOAuthRevocationLease(task); err != nil {
		return err
	}
	if now.IsZero() {
		now = time.Now().UTC()
	}
	return store.execLeaseTransition(
		ctx,
		task,
		"SELECT a1_complete_identity_revocation_outbox($1::uuid, $2::uuid, $3::uuid, $4, $5, $6)",
		"complete",
		now.UTC(),
	)
}

func (store *PostgresOAuthRevocationOutboxStore) RetryOAuthRevocation(
	ctx context.Context,
	task OAuthRevocationTask,
	errorCode string,
	baseBackoff time.Duration,
	maxBackoff time.Duration,
	now time.Time,
) (bool, time.Time, error) {
	if err := validateOAuthRevocationLease(task); err != nil {
		return false, time.Time{}, err
	}
	errorCode = strings.ToLower(strings.TrimSpace(errorCode))
	if !oauthRevocationErrorCodePattern.MatchString(errorCode) {
		return false, time.Time{}, fmt.Errorf("OAuth revocation error code is invalid")
	}
	if baseBackoff < time.Second || maxBackoff < baseBackoff || maxBackoff > 24*time.Hour {
		return false, time.Time{}, fmt.Errorf("OAuth revocation backoff configuration is invalid")
	}
	if now.IsZero() {
		now = time.Now().UTC()
	}
	baseSeconds := int64(baseBackoff / time.Second)
	maxSeconds := int64(maxBackoff / time.Second)
	organizationID, projectID := postgresOAuthScope(task.TenantID, task.ProjectID)
	tx, err := store.db.BeginTx(ctx, nil)
	if err != nil {
		return false, time.Time{}, fmt.Errorf("begin OAuth revocation retry: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	if err := setPostgresOAuthScopeNeutral(ctx, tx, organizationID, projectID); err != nil {
		return false, time.Time{}, err
	}
	var status string
	var availableAt time.Time
	err = tx.QueryRowContext(ctx, `
SELECT status, available_at
  FROM a1_retry_identity_revocation_outbox(
    $1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8
  )
`, organizationID, projectID, task.ID, task.LeaseOwner, task.LeaseGeneration,
		errorCode, baseSeconds, maxSeconds, now.UTC()).Scan(&status, &availableAt)
	if err != nil {
		return false, time.Time{}, mapOAuthRevocationTransitionError("retry", err)
	}
	if err := tx.Commit(); err != nil {
		return false, time.Time{}, fmt.Errorf("commit OAuth revocation retry: %w", err)
	}
	return status == "dead_letter", availableAt, nil
}

func (store *PostgresOAuthRevocationOutboxStore) execLeaseTransition(
	ctx context.Context,
	task OAuthRevocationTask,
	statement string,
	operation string,
	now time.Time,
) error {
	organizationID, projectID := postgresOAuthScope(task.TenantID, task.ProjectID)
	tx, err := store.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin OAuth revocation completion: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	if err := setPostgresOAuthScopeNeutral(ctx, tx, organizationID, projectID); err != nil {
		return err
	}
	if _, err := tx.ExecContext(
		ctx,
		statement,
		organizationID,
		projectID,
		task.ID,
		task.LeaseOwner,
		task.LeaseGeneration,
		now,
	); err != nil {
		return mapOAuthRevocationTransitionError(operation, err)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit OAuth revocation completion: %w", err)
	}
	return nil
}

func validateOAuthRevocationLease(task OAuthRevocationTask) error {
	for name, value := range map[string]string{
		"task_id": task.ID, "tenant_id": task.TenantID, "project_id": task.ProjectID,
		"provider": task.Provider, "token_ref_id": task.TokenRefID,
		"lease_owner": task.LeaseOwner,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("OAuth revocation %s is required", name)
		}
	}
	if task.LeaseGeneration < 1 {
		return fmt.Errorf("OAuth revocation lease generation must be positive")
	}
	return nil
}

func mapOAuthRevocationTransitionError(operation string, err error) error {
	var pqErr interface{ SQLState() string }
	if errors.As(err, &pqErr) && pqErr.SQLState() == "40001" {
		return fmt.Errorf("OAuth revocation lease lost during %s: %w", operation, err)
	}
	return fmt.Errorf("%s OAuth revocation outbox: %w", operation, err)
}

func oauthRevocationBackoff(attempt int, base, maximum time.Duration) time.Duration {
	if attempt <= 1 {
		return base
	}
	exponent := math.Min(float64(attempt-1), 30)
	backoff := float64(base) * math.Pow(2, exponent)
	if backoff >= float64(maximum) {
		return maximum
	}
	return time.Duration(backoff)
}

var _ OAuthRevocationOutboxStore = (*PostgresOAuthRevocationOutboxStore)(nil)
