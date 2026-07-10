package ashrclone

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"
)

const PaymentReconciliationSchemaVersion = "ashr.clone.payment_reconciliation.v1"

const (
	PaymentEventStatusReceived = "received"
	PaymentEventStatusVerified = "verified"
	PaymentEventStatusApplied  = "applied"
	PaymentEventStatusFailed   = "failed"
)

const PaymentReconciliationSchemaSQL = `
CREATE TABLE IF NOT EXISTS ashr_payment_reconciliation_events (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_event_id TEXT NOT NULL,
    event_type TEXT NOT NULL DEFAULT '',
    payload_sha256 TEXT NOT NULL,
    headers_sha256 TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'received',
    failure_sha256 TEXT NOT NULL DEFAULT '',
    received_at TIMESTAMPTZ NOT NULL,
    verified_at TIMESTAMPTZ,
    applied_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, project_id, provider, provider_event_id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES ashr_projects(tenant_id, project_id) ON DELETE CASCADE,
    CONSTRAINT ashr_payment_reconciliation_status CHECK (status IN ('received', 'verified', 'applied', 'failed')),
    CONSTRAINT ashr_payment_reconciliation_payload_hash CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ashr_payment_reconciliation_headers_hash CHECK (headers_sha256 = '' OR headers_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ashr_payment_reconciliation_failure_hash CHECK (failure_sha256 = '' OR failure_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ashr_payment_reconciliation_terminal_shape CHECK (
        (status = 'received' AND verified_at IS NULL AND applied_at IS NULL AND failed_at IS NULL AND failure_sha256 = '')
        OR (status = 'verified' AND verified_at IS NOT NULL AND applied_at IS NULL AND failed_at IS NULL AND failure_sha256 = '')
        OR (status = 'applied' AND verified_at IS NOT NULL AND applied_at IS NOT NULL AND failed_at IS NULL AND failure_sha256 = '')
        OR (status = 'failed' AND verified_at IS NOT NULL AND applied_at IS NULL AND failed_at IS NOT NULL AND failure_sha256 <> '')
    )
);

CREATE INDEX IF NOT EXISTS ashr_payment_reconciliation_scope_idx
    ON ashr_payment_reconciliation_events (tenant_id, project_id, status, received_at, provider_event_id);
`

var paymentSHA256Pattern = regexp.MustCompile(`^[0-9a-f]{64}$`)

type PaymentEventHashEnvelope struct {
	Provider        string `json:"provider"`
	ProviderEventID string `json:"provider_event_id"`
	EventType       string `json:"event_type,omitempty"`
	PayloadSHA256   string `json:"payload_sha256"`
	HeadersSHA256   string `json:"headers_sha256,omitempty"`
}

type PaymentReconciliationEvent struct {
	SchemaVersion      string     `json:"schema_version"`
	TenantID           string     `json:"tenant_id"`
	ProjectID          string     `json:"project_id"`
	Provider           string     `json:"provider"`
	ProviderEventID    string     `json:"provider_event_id"`
	EventType          string     `json:"event_type,omitempty"`
	PayloadSHA256      string     `json:"payload_sha256"`
	HeadersSHA256      string     `json:"headers_sha256,omitempty"`
	Status             string     `json:"status"`
	FailureSHA256      string     `json:"failure_sha256,omitempty"`
	RawPayloadIncluded bool       `json:"raw_payload_included"`
	RawHeadersIncluded bool       `json:"raw_headers_included"`
	SecretValuePresent bool       `json:"secret_value_present"`
	ReceivedAt         time.Time  `json:"received_at"`
	VerifiedAt         *time.Time `json:"verified_at,omitempty"`
	AppliedAt          *time.Time `json:"applied_at,omitempty"`
	FailedAt           *time.Time `json:"failed_at,omitempty"`
	UpdatedAt          time.Time  `json:"updated_at"`
}

type PaymentReconciliationList struct {
	SchemaVersion string                       `json:"schema_version"`
	TenantID      string                       `json:"tenant_id"`
	ProjectID     string                       `json:"project_id"`
	Status        string                       `json:"status,omitempty"`
	Events        []PaymentReconciliationEvent `json:"events"`
	Count         int                          `json:"count"`
}

type PaymentReconciliationConflictError struct {
	Provider        string
	ProviderEventID string
}

func (err PaymentReconciliationConflictError) Error() string {
	return fmt.Sprintf("payment event hash conflict for provider %q event %q", err.Provider, err.ProviderEventID)
}

type PaymentReconciliationTransitionError struct {
	Provider        string
	ProviderEventID string
	From            string
	To              string
}

func (err PaymentReconciliationTransitionError) Error() string {
	return fmt.Sprintf("invalid payment reconciliation transition for provider %q event %q: %s -> %s", err.Provider, err.ProviderEventID, err.From, err.To)
}

type PaymentReconciliationRepository interface {
	ReceivePaymentEvent(ctx context.Context, tenantID, projectID string, envelope PaymentEventHashEnvelope) (PaymentReconciliationEvent, bool, error)
	TransitionPaymentEvent(ctx context.Context, tenantID, projectID, provider, providerEventID, targetStatus, failureSHA256 string) (PaymentReconciliationEvent, bool, error)
	GetPaymentEvent(ctx context.Context, tenantID, projectID, provider, providerEventID string) (PaymentReconciliationEvent, error)
	ListPaymentEvents(ctx context.Context, tenantID, projectID, status string, limit int) (PaymentReconciliationList, error)
}

type PaymentReconciliationService struct {
	repository PaymentReconciliationRepository
}

func NewPaymentReconciliationService(repository PaymentReconciliationRepository) (*PaymentReconciliationService, error) {
	if repository == nil {
		return nil, fmt.Errorf("payment reconciliation repository is required")
	}
	return &PaymentReconciliationService{repository: repository}, nil
}

func (service *PaymentReconciliationService) Receive(ctx context.Context, tenantID, projectID string, envelope PaymentEventHashEnvelope) (Envelope[PaymentReconciliationEvent], error) {
	if err := validatePaymentScope(tenantID, projectID); err != nil {
		return Envelope[PaymentReconciliationEvent]{}, err
	}
	envelope = normalizePaymentEventEnvelope(envelope)
	if err := validatePaymentEventEnvelope(envelope); err != nil {
		return Envelope[PaymentReconciliationEvent]{}, err
	}
	event, replay, err := service.repository.ReceivePaymentEvent(ctx, tenantID, projectID, envelope)
	if err != nil {
		return Envelope[PaymentReconciliationEvent]{}, err
	}
	return Envelope[PaymentReconciliationEvent]{Operation: "payment.reconciliation.receive", Status: "ok", IdempotentReplay: replay, Result: publicPaymentEvent(event)}, nil
}

func (service *PaymentReconciliationService) Verify(ctx context.Context, tenantID, projectID, provider, providerEventID string) (Envelope[PaymentReconciliationEvent], error) {
	return service.transition(ctx, tenantID, projectID, provider, providerEventID, PaymentEventStatusVerified, "")
}

func (service *PaymentReconciliationService) Apply(ctx context.Context, tenantID, projectID, provider, providerEventID string) (Envelope[PaymentReconciliationEvent], error) {
	return service.transition(ctx, tenantID, projectID, provider, providerEventID, PaymentEventStatusApplied, "")
}

func (service *PaymentReconciliationService) Fail(ctx context.Context, tenantID, projectID, provider, providerEventID, failureSHA256 string) (Envelope[PaymentReconciliationEvent], error) {
	failureSHA256 = strings.ToLower(strings.TrimSpace(failureSHA256))
	if !paymentSHA256Pattern.MatchString(failureSHA256) {
		return Envelope[PaymentReconciliationEvent]{}, fmt.Errorf("failure_sha256 must be a lowercase SHA-256 digest")
	}
	return service.transition(ctx, tenantID, projectID, provider, providerEventID, PaymentEventStatusFailed, failureSHA256)
}

func (service *PaymentReconciliationService) Get(ctx context.Context, tenantID, projectID, provider, providerEventID string) (Envelope[PaymentReconciliationEvent], error) {
	if err := validatePaymentEventIdentity(tenantID, projectID, provider, providerEventID); err != nil {
		return Envelope[PaymentReconciliationEvent]{}, err
	}
	event, err := service.repository.GetPaymentEvent(ctx, tenantID, projectID, normalizeProvider(provider), strings.TrimSpace(providerEventID))
	if err != nil {
		return Envelope[PaymentReconciliationEvent]{}, err
	}
	return Envelope[PaymentReconciliationEvent]{Operation: "payment.reconciliation.get", Status: "ok", Result: publicPaymentEvent(event)}, nil
}

func (service *PaymentReconciliationService) List(ctx context.Context, tenantID, projectID, status string, limit int) (Envelope[PaymentReconciliationList], error) {
	if err := validatePaymentScope(tenantID, projectID); err != nil {
		return Envelope[PaymentReconciliationList]{}, err
	}
	status = strings.ToLower(strings.TrimSpace(status))
	if status != "" && !validPaymentEventStatus(status) {
		return Envelope[PaymentReconciliationList]{}, fmt.Errorf("invalid payment reconciliation status %q", status)
	}
	result, err := service.repository.ListPaymentEvents(ctx, tenantID, projectID, status, limit)
	if err != nil {
		return Envelope[PaymentReconciliationList]{}, err
	}
	for index := range result.Events {
		result.Events[index] = publicPaymentEvent(result.Events[index])
	}
	return Envelope[PaymentReconciliationList]{Operation: "payment.reconciliation.list", Status: "ok", Result: result}, nil
}

func (service *PaymentReconciliationService) transition(ctx context.Context, tenantID, projectID, provider, providerEventID, status, failureSHA256 string) (Envelope[PaymentReconciliationEvent], error) {
	if err := validatePaymentEventIdentity(tenantID, projectID, provider, providerEventID); err != nil {
		return Envelope[PaymentReconciliationEvent]{}, err
	}
	event, replay, err := service.repository.TransitionPaymentEvent(ctx, tenantID, projectID, normalizeProvider(provider), strings.TrimSpace(providerEventID), status, failureSHA256)
	if err != nil {
		return Envelope[PaymentReconciliationEvent]{}, err
	}
	return Envelope[PaymentReconciliationEvent]{Operation: "payment.reconciliation." + status, Status: "ok", IdempotentReplay: replay, Result: publicPaymentEvent(event)}, nil
}

type MemoryPaymentReconciliationRepository struct {
	mu     sync.Mutex
	now    func() time.Time
	events map[string]PaymentReconciliationEvent
}

func NewMemoryPaymentReconciliationRepository() *MemoryPaymentReconciliationRepository {
	return &MemoryPaymentReconciliationRepository{
		now:    func() time.Time { return time.Now().UTC() },
		events: map[string]PaymentReconciliationEvent{},
	}
}

func (repository *MemoryPaymentReconciliationRepository) ReceivePaymentEvent(_ context.Context, tenantID, projectID string, envelope PaymentEventHashEnvelope) (PaymentReconciliationEvent, bool, error) {
	repository.mu.Lock()
	defer repository.mu.Unlock()
	key := paymentEventKey(tenantID, projectID, envelope.Provider, envelope.ProviderEventID)
	if stored, ok := repository.events[key]; ok {
		if stored.PayloadSHA256 != envelope.PayloadSHA256 || stored.HeadersSHA256 != envelope.HeadersSHA256 {
			return PaymentReconciliationEvent{}, false, PaymentReconciliationConflictError{Provider: envelope.Provider, ProviderEventID: envelope.ProviderEventID}
		}
		return publicPaymentEvent(stored), true, nil
	}
	now := repository.now().UTC()
	event := PaymentReconciliationEvent{
		SchemaVersion: PaymentReconciliationSchemaVersion,
		TenantID:      tenantID, ProjectID: projectID, Provider: envelope.Provider,
		ProviderEventID: envelope.ProviderEventID, EventType: envelope.EventType,
		PayloadSHA256: envelope.PayloadSHA256, HeadersSHA256: envelope.HeadersSHA256,
		Status: PaymentEventStatusReceived, ReceivedAt: now, UpdatedAt: now,
	}
	repository.events[key] = event
	return publicPaymentEvent(event), false, nil
}

func (repository *MemoryPaymentReconciliationRepository) TransitionPaymentEvent(_ context.Context, tenantID, projectID, provider, providerEventID, targetStatus, failureSHA256 string) (PaymentReconciliationEvent, bool, error) {
	repository.mu.Lock()
	defer repository.mu.Unlock()
	key := paymentEventKey(tenantID, projectID, provider, providerEventID)
	event, ok := repository.events[key]
	if !ok {
		return PaymentReconciliationEvent{}, false, NotFoundError{Resource: "payment reconciliation event"}
	}
	if event.Status == targetStatus {
		if targetStatus == PaymentEventStatusFailed && event.FailureSHA256 != failureSHA256 {
			return PaymentReconciliationEvent{}, false, PaymentReconciliationConflictError{Provider: provider, ProviderEventID: providerEventID}
		}
		return publicPaymentEvent(event), true, nil
	}
	if !allowedPaymentTransition(event.Status, targetStatus) {
		return PaymentReconciliationEvent{}, false, PaymentReconciliationTransitionError{Provider: provider, ProviderEventID: providerEventID, From: event.Status, To: targetStatus}
	}
	now := repository.now().UTC()
	event.Status = targetStatus
	event.UpdatedAt = now
	switch targetStatus {
	case PaymentEventStatusVerified:
		event.VerifiedAt = paymentTimePointer(now)
	case PaymentEventStatusApplied:
		event.AppliedAt = paymentTimePointer(now)
	case PaymentEventStatusFailed:
		event.FailedAt = paymentTimePointer(now)
		event.FailureSHA256 = failureSHA256
	}
	repository.events[key] = event
	return publicPaymentEvent(event), false, nil
}

func (repository *MemoryPaymentReconciliationRepository) GetPaymentEvent(_ context.Context, tenantID, projectID, provider, providerEventID string) (PaymentReconciliationEvent, error) {
	repository.mu.Lock()
	defer repository.mu.Unlock()
	event, ok := repository.events[paymentEventKey(tenantID, projectID, provider, providerEventID)]
	if !ok {
		return PaymentReconciliationEvent{}, NotFoundError{Resource: "payment reconciliation event"}
	}
	return publicPaymentEvent(event), nil
}

func (repository *MemoryPaymentReconciliationRepository) ListPaymentEvents(_ context.Context, tenantID, projectID, status string, limit int) (PaymentReconciliationList, error) {
	repository.mu.Lock()
	defer repository.mu.Unlock()
	limit = normalizePaymentListLimit(limit)
	events := make([]PaymentReconciliationEvent, 0, len(repository.events))
	for _, event := range repository.events {
		if event.TenantID == tenantID && event.ProjectID == projectID && (status == "" || event.Status == status) {
			events = append(events, publicPaymentEvent(event))
		}
	}
	sort.Slice(events, func(i, j int) bool {
		if !events[i].ReceivedAt.Equal(events[j].ReceivedAt) {
			return events[i].ReceivedAt.Before(events[j].ReceivedAt)
		}
		if events[i].Provider != events[j].Provider {
			return events[i].Provider < events[j].Provider
		}
		return events[i].ProviderEventID < events[j].ProviderEventID
	})
	if len(events) > limit {
		events = events[:limit]
	}
	return PaymentReconciliationList{SchemaVersion: PaymentReconciliationSchemaVersion, TenantID: tenantID, ProjectID: projectID, Status: status, Events: events, Count: len(events)}, nil
}

func MigratePaymentReconciliationPostgres(ctx context.Context, db *sql.DB) error {
	if db == nil {
		return fmt.Errorf("postgres db is required")
	}
	if _, err := db.ExecContext(ctx, PaymentReconciliationSchemaSQL); err != nil {
		return fmt.Errorf("migrate payment reconciliation schema: %w", err)
	}
	return nil
}

func (repository *PostgresRepository) MigratePaymentReconciliation(ctx context.Context) error {
	if repository == nil || repository.db == nil {
		return fmt.Errorf("postgres db is required")
	}
	return MigratePaymentReconciliationPostgres(ctx, repository.db)
}

func (repository *PostgresRepository) ReceivePaymentEvent(ctx context.Context, tenantID, projectID string, envelope PaymentEventHashEnvelope) (PaymentReconciliationEvent, bool, error) {
	if repository == nil || repository.db == nil {
		return PaymentReconciliationEvent{}, false, fmt.Errorf("postgres db is required")
	}
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return PaymentReconciliationEvent{}, false, fmt.Errorf("receive payment event begin transaction: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	now := repository.now().UTC()
	result, err := tx.ExecContext(ctx, `
INSERT INTO ashr_payment_reconciliation_events (
    tenant_id, project_id, provider, provider_event_id, event_type, payload_sha256, headers_sha256,
    status, received_at, updated_at
) VALUES ($1, $2, $3, $4, $5, $6, $7, 'received', $8, $8)
ON CONFLICT (tenant_id, project_id, provider, provider_event_id) DO NOTHING
`, tenantID, projectID, envelope.Provider, envelope.ProviderEventID, envelope.EventType, envelope.PayloadSHA256, envelope.HeadersSHA256, now)
	if err != nil {
		return PaymentReconciliationEvent{}, false, fmt.Errorf("receive payment event insert: %w", err)
	}
	rows, err := result.RowsAffected()
	if err != nil {
		return PaymentReconciliationEvent{}, false, fmt.Errorf("receive payment event rows affected: %w", err)
	}
	event, err := scanPaymentEvent(tx.QueryRowContext(ctx, paymentEventSelectSQL+`
WHERE tenant_id = $1 AND project_id = $2 AND provider = $3 AND provider_event_id = $4
FOR UPDATE
`, tenantID, projectID, envelope.Provider, envelope.ProviderEventID))
	if err != nil {
		return PaymentReconciliationEvent{}, false, fmt.Errorf("receive payment event select: %w", err)
	}
	if event.PayloadSHA256 != envelope.PayloadSHA256 || event.HeadersSHA256 != envelope.HeadersSHA256 {
		return PaymentReconciliationEvent{}, false, PaymentReconciliationConflictError{Provider: envelope.Provider, ProviderEventID: envelope.ProviderEventID}
	}
	if err := tx.Commit(); err != nil {
		return PaymentReconciliationEvent{}, false, fmt.Errorf("receive payment event commit: %w", err)
	}
	return publicPaymentEvent(event), rows == 0, nil
}

func (repository *PostgresRepository) TransitionPaymentEvent(ctx context.Context, tenantID, projectID, provider, providerEventID, targetStatus, failureSHA256 string) (PaymentReconciliationEvent, bool, error) {
	if repository == nil || repository.db == nil {
		return PaymentReconciliationEvent{}, false, fmt.Errorf("postgres db is required")
	}
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return PaymentReconciliationEvent{}, false, fmt.Errorf("transition payment event begin transaction: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	event, err := scanPaymentEvent(tx.QueryRowContext(ctx, paymentEventSelectSQL+`
WHERE tenant_id = $1 AND project_id = $2 AND provider = $3 AND provider_event_id = $4
FOR UPDATE
`, tenantID, projectID, provider, providerEventID))
	if errors.Is(err, sql.ErrNoRows) {
		return PaymentReconciliationEvent{}, false, NotFoundError{Resource: "payment reconciliation event"}
	}
	if err != nil {
		return PaymentReconciliationEvent{}, false, fmt.Errorf("transition payment event select: %w", err)
	}
	if event.Status == targetStatus {
		if targetStatus == PaymentEventStatusFailed && event.FailureSHA256 != failureSHA256 {
			return PaymentReconciliationEvent{}, false, PaymentReconciliationConflictError{Provider: provider, ProviderEventID: providerEventID}
		}
		if err := tx.Commit(); err != nil {
			return PaymentReconciliationEvent{}, false, fmt.Errorf("replay payment event transition commit: %w", err)
		}
		return publicPaymentEvent(event), true, nil
	}
	if !allowedPaymentTransition(event.Status, targetStatus) {
		return PaymentReconciliationEvent{}, false, PaymentReconciliationTransitionError{Provider: provider, ProviderEventID: providerEventID, From: event.Status, To: targetStatus}
	}
	now := repository.now().UTC()
	verifiedAt, appliedAt, failedAt := event.VerifiedAt, event.AppliedAt, event.FailedAt
	switch targetStatus {
	case PaymentEventStatusVerified:
		verifiedAt = paymentTimePointer(now)
	case PaymentEventStatusApplied:
		appliedAt = paymentTimePointer(now)
	case PaymentEventStatusFailed:
		failedAt = paymentTimePointer(now)
	}
	updated, err := scanPaymentEvent(tx.QueryRowContext(ctx, `
UPDATE ashr_payment_reconciliation_events
SET status = $5, failure_sha256 = $6, verified_at = $7, applied_at = $8, failed_at = $9, updated_at = $10
WHERE tenant_id = $1 AND project_id = $2 AND provider = $3 AND provider_event_id = $4
RETURNING tenant_id, project_id, provider, provider_event_id, event_type, payload_sha256, headers_sha256,
          status, failure_sha256, received_at, verified_at, applied_at, failed_at, updated_at
`, tenantID, projectID, provider, providerEventID, targetStatus, failureSHA256, verifiedAt, appliedAt, failedAt, now))
	if err != nil {
		return PaymentReconciliationEvent{}, false, fmt.Errorf("transition payment event update: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return PaymentReconciliationEvent{}, false, fmt.Errorf("transition payment event commit: %w", err)
	}
	return publicPaymentEvent(updated), false, nil
}

func (repository *PostgresRepository) GetPaymentEvent(ctx context.Context, tenantID, projectID, provider, providerEventID string) (PaymentReconciliationEvent, error) {
	if repository == nil || repository.db == nil {
		return PaymentReconciliationEvent{}, fmt.Errorf("postgres db is required")
	}
	event, err := scanPaymentEvent(repository.db.QueryRowContext(ctx, paymentEventSelectSQL+`
WHERE tenant_id = $1 AND project_id = $2 AND provider = $3 AND provider_event_id = $4
`, tenantID, projectID, provider, providerEventID))
	if errors.Is(err, sql.ErrNoRows) {
		return PaymentReconciliationEvent{}, NotFoundError{Resource: "payment reconciliation event"}
	}
	if err != nil {
		return PaymentReconciliationEvent{}, fmt.Errorf("get payment event: %w", err)
	}
	return publicPaymentEvent(event), nil
}

func (repository *PostgresRepository) ListPaymentEvents(ctx context.Context, tenantID, projectID, status string, limit int) (PaymentReconciliationList, error) {
	if repository == nil || repository.db == nil {
		return PaymentReconciliationList{}, fmt.Errorf("postgres db is required")
	}
	limit = normalizePaymentListLimit(limit)
	rows, err := repository.db.QueryContext(ctx, paymentEventSelectSQL+`
WHERE tenant_id = $1 AND project_id = $2 AND ($3 = '' OR status = $3)
ORDER BY received_at ASC, provider ASC, provider_event_id ASC
LIMIT $4
`, tenantID, projectID, status, limit)
	if err != nil {
		return PaymentReconciliationList{}, fmt.Errorf("list payment events: %w", err)
	}
	defer rows.Close()
	events := make([]PaymentReconciliationEvent, 0, limit)
	for rows.Next() {
		event, scanErr := scanPaymentEvent(rows)
		if scanErr != nil {
			return PaymentReconciliationList{}, fmt.Errorf("list payment events scan: %w", scanErr)
		}
		events = append(events, publicPaymentEvent(event))
	}
	if err := rows.Err(); err != nil {
		return PaymentReconciliationList{}, fmt.Errorf("list payment events rows: %w", err)
	}
	return PaymentReconciliationList{SchemaVersion: PaymentReconciliationSchemaVersion, TenantID: tenantID, ProjectID: projectID, Status: status, Events: events, Count: len(events)}, nil
}

const paymentEventSelectSQL = `
SELECT tenant_id, project_id, provider, provider_event_id, event_type, payload_sha256, headers_sha256,
       status, failure_sha256, received_at, verified_at, applied_at, failed_at, updated_at
FROM ashr_payment_reconciliation_events
`

type paymentEventScanner interface {
	Scan(dest ...any) error
}

func scanPaymentEvent(scanner paymentEventScanner) (PaymentReconciliationEvent, error) {
	event := PaymentReconciliationEvent{SchemaVersion: PaymentReconciliationSchemaVersion}
	err := scanner.Scan(
		&event.TenantID, &event.ProjectID, &event.Provider, &event.ProviderEventID, &event.EventType,
		&event.PayloadSHA256, &event.HeadersSHA256, &event.Status, &event.FailureSHA256,
		&event.ReceivedAt, &event.VerifiedAt, &event.AppliedAt, &event.FailedAt, &event.UpdatedAt,
	)
	return publicPaymentEvent(event), err
}

func normalizePaymentEventEnvelope(envelope PaymentEventHashEnvelope) PaymentEventHashEnvelope {
	envelope.Provider = normalizeProvider(envelope.Provider)
	envelope.ProviderEventID = strings.TrimSpace(envelope.ProviderEventID)
	envelope.EventType = strings.TrimSpace(envelope.EventType)
	envelope.PayloadSHA256 = strings.ToLower(strings.TrimSpace(envelope.PayloadSHA256))
	envelope.HeadersSHA256 = strings.ToLower(strings.TrimSpace(envelope.HeadersSHA256))
	return envelope
}

func normalizeProvider(provider string) string {
	return strings.ToLower(strings.TrimSpace(provider))
}

func validatePaymentScope(tenantID, projectID string) error {
	if strings.TrimSpace(tenantID) == "" {
		return fmt.Errorf("tenant_id is required")
	}
	if strings.TrimSpace(projectID) == "" {
		return fmt.Errorf("project_id is required")
	}
	return nil
}

func validatePaymentEventIdentity(tenantID, projectID, provider, providerEventID string) error {
	if err := validatePaymentScope(tenantID, projectID); err != nil {
		return err
	}
	if normalizeProvider(provider) == "" {
		return fmt.Errorf("provider is required")
	}
	if strings.TrimSpace(providerEventID) == "" {
		return fmt.Errorf("provider_event_id is required")
	}
	return nil
}

func validatePaymentEventEnvelope(envelope PaymentEventHashEnvelope) error {
	if envelope.Provider == "" {
		return fmt.Errorf("provider is required")
	}
	if envelope.ProviderEventID == "" {
		return fmt.Errorf("provider_event_id is required")
	}
	if !paymentSHA256Pattern.MatchString(envelope.PayloadSHA256) {
		return fmt.Errorf("payload_sha256 must be a lowercase SHA-256 digest")
	}
	if envelope.HeadersSHA256 != "" && !paymentSHA256Pattern.MatchString(envelope.HeadersSHA256) {
		return fmt.Errorf("headers_sha256 must be a lowercase SHA-256 digest")
	}
	return nil
}

func validPaymentEventStatus(status string) bool {
	switch status {
	case PaymentEventStatusReceived, PaymentEventStatusVerified, PaymentEventStatusApplied, PaymentEventStatusFailed:
		return true
	default:
		return false
	}
}

func allowedPaymentTransition(from, to string) bool {
	return (from == PaymentEventStatusReceived && to == PaymentEventStatusVerified) ||
		(from == PaymentEventStatusVerified && (to == PaymentEventStatusApplied || to == PaymentEventStatusFailed))
}

func paymentEventKey(tenantID, projectID, provider, providerEventID string) string {
	return tenantID + "\x00" + projectID + "\x00" + provider + "\x00" + providerEventID
}

func publicPaymentEvent(event PaymentReconciliationEvent) PaymentReconciliationEvent {
	event.SchemaVersion = PaymentReconciliationSchemaVersion
	event.RawPayloadIncluded = false
	event.RawHeadersIncluded = false
	event.SecretValuePresent = false
	return event
}

func normalizePaymentListLimit(limit int) int {
	if limit <= 0 {
		return 100
	}
	if limit > 500 {
		return 500
	}
	return limit
}

func paymentTimePointer(value time.Time) *time.Time {
	copy := value
	return &copy
}

var _ PaymentReconciliationRepository = (*MemoryPaymentReconciliationRepository)(nil)
var _ PaymentReconciliationRepository = (*PostgresRepository)(nil)
