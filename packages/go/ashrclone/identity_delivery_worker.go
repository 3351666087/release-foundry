package ashrclone

import (
	"context"
	cryptorand "crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"math/big"
	"regexp"
	"strings"
	"sync"
	"time"
)

const IdentityDeliveryTelemetrySchemaVersion = "ashr.identity_delivery.telemetry.v1"

const (
	IdentityDeliveryEventDelivered      = "identity.delivery.delivered"
	IdentityDeliveryEventRetryScheduled = "identity.delivery.retry_scheduled"
	IdentityDeliveryEventDeadLettered   = "identity.delivery.dead_lettered"
	IdentityDeliveryEventLeaseRejected  = "identity.delivery.lease_rejected"
	IdentityDeliveryEventRedriven       = "identity.delivery.redriven"
)

const (
	identityDeliveryFailureMalformedTask     = "malformed_task"
	identityDeliveryFailureMalformedPayload  = "malformed_payload"
	identityDeliveryFailureChallengeExpired  = "challenge_expired"
	identityDeliveryFailureAttemptsExhausted = "attempts_exhausted"
	identityDeliveryFailureVaultUnavailable  = "vault_unavailable"
	identityDeliveryFailureVaultTimeout      = "vault_timeout"
	identityDeliveryFailureSMTP              = "smtp_delivery_failed"
	identityDeliveryFailureSMS               = "sms_delivery_failed"
	identityDeliveryFailureProviderTimeout   = "provider_timeout"
	identityDeliveryFailureProviderUnknown   = "provider_outcome_unknown"
	identityDeliveryFailureLeaseExpired      = "lease_expired"
	identityDeliveryFailureLeaseLost         = "lease_lost"
)

var (
	ErrIdentityDeliveryLeaseLost        = errors.New("identity delivery lease lost")
	ErrIdentityDeliveryLeaseExpired     = errors.New("identity delivery lease expired")
	ErrIdentityDeliveryScope            = errors.New("identity delivery scope mismatch")
	errIdentityDeliveryChallengeExpired = errors.New("identity delivery challenge expired")
)

var identityDeliveryIdentifierPattern = regexp.MustCompile(
	`^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$`,
)
var identityDeliveryOpaqueReferencePattern = regexp.MustCompile(
	`^(vault|env|kms|secret|provider-ref|opaque-ref):[A-Za-z0-9][A-Za-z0-9._:/-]{1,1000}$`,
)
var identityDeliveryReasonPattern = regexp.MustCompile(`^[a-z][a-z0-9_.-]{1,63}$`)
var identityDeliveryProviderAcceptancePattern = regexp.MustCompile(
	`^(provider-ref|message-ref|receipt-ref):[A-Za-z0-9][A-Za-z0-9._:/-]*$`,
)

// IdentityDeliveryTask contains a fenced lease and an opaque secret reference.
// Destination and verification code material must never be stored in this value.
type IdentityDeliveryTask struct {
	ID                     string
	TenantID               string
	ProjectID              string
	ChallengeID            string
	Channel                IdentityVerificationChannel
	Purpose                IdentityVerificationPurpose
	OpaqueRef              string
	ChallengeExpiresAt     time.Time
	Attempt                int
	MaxAttempts            int
	ProviderIdempotencyKey string
	LeaseOwner             string
	LeaseGeneration        int64
	LeaseExpiresAt         time.Time
}

// IdentityDeliverySecret is an ephemeral vault result. The binding fields are
// verified against the leased task before an adapter can observe the payload.
type IdentityDeliverySecret struct {
	TaskID      string
	TenantID    string
	ProjectID   string
	ChallengeID string
	Channel     IdentityVerificationChannel
	Destination string
	Code        string
}

type IdentityDeliveryVault interface {
	OpenIdentityDelivery(context.Context, string) (IdentityDeliverySecret, error)
}

type IdentityDeliveryProviderAcceptance struct {
	Reference  string
	AcceptedAt time.Time
}

// IdentityDeliveryAcceptanceAdapter is the receipt-aware provider contract.
// Implementations must use delivery.ProviderIdempotencyKey for every retry.
type IdentityDeliveryAcceptanceAdapter interface {
	SendIdentityVerificationWithAcceptance(
		context.Context,
		IdentityVerificationDelivery,
	) (IdentityDeliveryProviderAcceptance, error)
}

// IdentityDeliveryAdapter is retained for relay compatibility. The worker
// derives a deterministic public acceptance reference when a legacy relay
// acknowledges a request without returning its own receipt.
type IdentityDeliveryAdapter interface {
	SendIdentityVerification(context.Context, IdentityVerificationDelivery) error
}

// Separate capabilities keep SMTP and SMS provider configuration opaque to the worker.
type IdentityDeliverySMTPAdapter interface {
	IdentityDeliveryAdapter
}

type IdentityDeliverySMSAdapter interface {
	IdentityDeliveryAdapter
}

// IdentityDeliveryOutboxStore is the durable compare-and-swap boundary.
// Heartbeat and every completion, retry, and dead-letter transition must
// atomically match ID, scope, lease owner, lease generation, leased status,
// and lease_expires_at > now. A compare-and-swap miss must wrap one of the
// exported lease errors so the worker never mistakes fence loss for retryable
// provider failure.
// Redrive must atomically update only a dead task, advance its generation, and
// append an immutable audit record before returning a receipt.
type IdentityDeliveryOutboxStore interface {
	ClaimIdentityDeliveries(
		context.Context,
		string,
		string,
		string,
		int,
		time.Duration,
		time.Time,
	) ([]IdentityDeliveryTask, error)
	HeartbeatIdentityDelivery(
		context.Context,
		IdentityDeliveryTask,
		time.Duration,
		time.Time,
	) (IdentityDeliveryTask, error)
	CompleteIdentityDelivery(
		context.Context,
		IdentityDeliveryTask,
		IdentityDeliveryProviderAcceptance,
		time.Time,
	) error
	RetryIdentityDelivery(
		context.Context,
		IdentityDeliveryTask,
		string,
		time.Time,
		time.Time,
	) error
	DeadLetterIdentityDelivery(
		context.Context,
		IdentityDeliveryTask,
		string,
		time.Time,
	) error
	RedriveIdentityDelivery(
		context.Context,
		IdentityDeliveryRedriveCommand,
	) (IdentityDeliveryRedriveReceipt, error)
}

type IdentityDeliveryRedriveRequest struct {
	TaskID                  string
	TenantID                string
	ProjectID               string
	ExpectedLeaseGeneration int64
	ActorID                 string
	ReasonCode              string
	RequestID               string
}

type IdentityDeliveryRedriveCommand struct {
	IdentityDeliveryRedriveRequest
	RequestedAt time.Time
}

type IdentityDeliveryRedriveReceipt struct {
	TaskID          string
	LeaseGeneration int64
	AuditID         string
	RedrivenAt      time.Time
}

// IdentityDeliveryTelemetryEvent deliberately has no task, destination,
// challenge, opaque-reference, error-message, tenant, or project fields.
type IdentityDeliveryTelemetryEvent struct {
	SchemaVersion string                      `json:"schema_version"`
	Type          string                      `json:"type"`
	Channel       IdentityVerificationChannel `json:"channel,omitempty"`
	Purpose       IdentityVerificationPurpose `json:"purpose,omitempty"`
	FailureCode   string                      `json:"failure_code,omitempty"`
	Attempt       int                         `json:"attempt,omitempty"`
	MaxAttempts   int                         `json:"max_attempts,omitempty"`
	RetryDelayMS  int64                       `json:"retry_delay_ms,omitempty"`
	OccurredAt    time.Time                   `json:"occurred_at"`
}

type IdentityDeliveryTelemetry interface {
	RecordIdentityDelivery(context.Context, IdentityDeliveryTelemetryEvent) error
}

type IdentityDeliveryTelemetryFunc func(context.Context, IdentityDeliveryTelemetryEvent) error

func (fn IdentityDeliveryTelemetryFunc) RecordIdentityDelivery(
	ctx context.Context,
	event IdentityDeliveryTelemetryEvent,
) error {
	return fn(ctx, event)
}

// IdentityDeliveryJitter receives the capped exponential delay and returns
// the final delay. Results are clamped to [0, MaxBackoff].
type IdentityDeliveryJitter func(time.Duration) time.Duration

type IdentityDeliveryWorkerOptions struct {
	Store             IdentityDeliveryOutboxStore
	Vault             IdentityDeliveryVault
	SMTP              IdentityDeliverySMTPAdapter
	SMS               IdentityDeliverySMSAdapter
	Telemetry         IdentityDeliveryTelemetry
	LeaseOwner        string
	LeaseDuration     time.Duration
	HeartbeatInterval time.Duration
	ProviderTimeout   time.Duration
	VaultTimeout      time.Duration
	StoreTimeout      time.Duration
	TelemetryTimeout  time.Duration
	BaseBackoff       time.Duration
	MaxBackoff        time.Duration
	MaxAttempts       int
	Jitter            IdentityDeliveryJitter
	Now               func() time.Time
}

type IdentityDeliveryWorker struct {
	store             IdentityDeliveryOutboxStore
	vault             IdentityDeliveryVault
	smtp              IdentityDeliverySMTPAdapter
	sms               IdentityDeliverySMSAdapter
	telemetry         IdentityDeliveryTelemetry
	leaseOwner        string
	leaseDuration     time.Duration
	heartbeatInterval time.Duration
	providerTimeout   time.Duration
	vaultTimeout      time.Duration
	storeTimeout      time.Duration
	telemetryTimeout  time.Duration
	baseBackoff       time.Duration
	maxBackoff        time.Duration
	maxAttempts       int
	jitter            IdentityDeliveryJitter
	now               func() time.Time
}

type IdentityDeliveryBatchResult struct {
	Claimed           int
	Delivered         int
	Retried           int
	DeadLettered      int
	LeaseRejected     int
	Heartbeats        int
	TelemetryFailures int
	Events            []IdentityDeliveryTelemetryEvent
}

type IdentityDeliveryDaemonOptions struct {
	TenantID     string
	ProjectID    string
	BatchSize    int
	PollInterval time.Duration
}

type IdentityDeliveryRunResult struct {
	Batches           int
	Claimed           int
	Delivered         int
	Retried           int
	DeadLettered      int
	LeaseRejected     int
	Heartbeats        int
	TelemetryFailures int
	GracefulShutdown  bool
	StartedAt         time.Time
	FinishedAt        time.Time
}

type identityDeliveryDisposition int

const (
	identityDeliveryUnchanged identityDeliveryDisposition = iota
	identityDeliveryDelivered
	identityDeliveryRetried
	identityDeliveryDeadLettered
	identityDeliveryLeaseRejected
)

type identityDeliveryTaskResult struct {
	disposition identityDeliveryDisposition
	heartbeats  int
	event       *IdentityDeliveryTelemetryEvent
	err         error
}

func NewIdentityDeliveryWorker(
	options IdentityDeliveryWorkerOptions,
) (*IdentityDeliveryWorker, error) {
	if options.Store == nil || options.Vault == nil || options.SMTP == nil || options.SMS == nil {
		return nil, fmt.Errorf("identity delivery store, vault, SMTP, and SMS adapters are required")
	}
	if !validIdentityDeliveryIdentifier(options.LeaseOwner) {
		return nil, fmt.Errorf("identity delivery lease owner is invalid")
	}
	if options.LeaseDuration == 0 {
		options.LeaseDuration = 30 * time.Second
	}
	if options.LeaseDuration < 100*time.Millisecond || options.LeaseDuration > time.Hour {
		return nil, fmt.Errorf("identity delivery lease duration must be between 100ms and 1h")
	}
	if options.HeartbeatInterval == 0 {
		options.HeartbeatInterval = options.LeaseDuration / 3
	}
	if options.HeartbeatInterval < time.Millisecond ||
		options.HeartbeatInterval >= options.LeaseDuration/2 {
		return nil, fmt.Errorf("identity delivery heartbeat interval must be at least 1ms and shorter than half the lease")
	}
	if options.ProviderTimeout == 0 {
		options.ProviderTimeout = minIdentityDeliveryDuration(10*time.Second, options.LeaseDuration/2)
	}
	if options.VaultTimeout == 0 {
		options.VaultTimeout = minIdentityDeliveryDuration(5*time.Second, options.LeaseDuration/2)
	}
	if options.StoreTimeout == 0 {
		options.StoreTimeout = minIdentityDeliveryDuration(5*time.Second, options.LeaseDuration/3)
	}
	if options.TelemetryTimeout == 0 {
		options.TelemetryTimeout = minIdentityDeliveryDuration(time.Second, options.LeaseDuration/3)
	}
	for name, value := range map[string]time.Duration{
		"provider":  options.ProviderTimeout,
		"vault":     options.VaultTimeout,
		"store":     options.StoreTimeout,
		"telemetry": options.TelemetryTimeout,
	} {
		if value < time.Millisecond || value >= options.LeaseDuration {
			return nil, fmt.Errorf("identity delivery %s timeout must be at least 1ms and shorter than the lease", name)
		}
	}
	if options.BaseBackoff == 0 {
		options.BaseBackoff = time.Second
	}
	if options.MaxBackoff == 0 {
		options.MaxBackoff = time.Hour
	}
	if options.BaseBackoff < time.Millisecond || options.MaxBackoff < options.BaseBackoff ||
		options.MaxBackoff > 24*time.Hour {
		return nil, fmt.Errorf("identity delivery backoff configuration is invalid")
	}
	if options.MaxAttempts == 0 {
		options.MaxAttempts = 8
	}
	if options.MaxAttempts < 1 || options.MaxAttempts > 1000 {
		return nil, fmt.Errorf("identity delivery max attempts must be between 1 and 1000")
	}
	if options.Jitter == nil {
		options.Jitter = defaultIdentityDeliveryJitter
	}
	if options.Now == nil {
		options.Now = time.Now
	}
	return &IdentityDeliveryWorker{
		store: options.Store, vault: options.Vault, smtp: options.SMTP, sms: options.SMS,
		telemetry: options.Telemetry, leaseOwner: options.LeaseOwner,
		leaseDuration: options.LeaseDuration, heartbeatInterval: options.HeartbeatInterval,
		providerTimeout: options.ProviderTimeout, vaultTimeout: options.VaultTimeout,
		storeTimeout: options.StoreTimeout, telemetryTimeout: options.TelemetryTimeout,
		baseBackoff: options.BaseBackoff, maxBackoff: options.MaxBackoff,
		maxAttempts: options.MaxAttempts, jitter: options.Jitter, now: options.Now,
	}, nil
}

func (worker *IdentityDeliveryWorker) ProcessBatch(
	ctx context.Context,
	tenantID string,
	projectID string,
	limit int,
) (IdentityDeliveryBatchResult, error) {
	result := IdentityDeliveryBatchResult{Events: []IdentityDeliveryTelemetryEvent{}}
	if err := validateIdentityDeliveryScope(tenantID, projectID); err != nil {
		return result, err
	}
	if limit < 1 || limit > 500 {
		return result, fmt.Errorf("identity delivery claim limit must be between 1 and 500")
	}
	if err := ctx.Err(); err != nil {
		return result, err
	}
	now := worker.nowUTC()
	storeCtx, cancel := context.WithTimeout(ctx, worker.storeTimeout)
	tasks, err := worker.store.ClaimIdentityDeliveries(
		storeCtx, tenantID, projectID, worker.leaseOwner, limit, worker.leaseDuration, now,
	)
	cancel()
	if err != nil {
		if ctxErr := ctx.Err(); ctxErr != nil {
			return result, ctxErr
		}
		return result, fmt.Errorf("claim identity delivery outbox: %w", err)
	}
	result.Claimed = len(tasks)
	var batchErrors []error
	for _, task := range tasks {
		if err := ctx.Err(); err != nil {
			batchErrors = append(batchErrors, err)
			break
		}
		taskResult := worker.processClaimedTask(ctx, tenantID, projectID, task)
		result.Heartbeats += taskResult.heartbeats
		switch taskResult.disposition {
		case identityDeliveryDelivered:
			result.Delivered++
		case identityDeliveryRetried:
			result.Retried++
		case identityDeliveryDeadLettered:
			result.DeadLettered++
		case identityDeliveryLeaseRejected:
			result.LeaseRejected++
		}
		if taskResult.event != nil {
			result.Events = append(result.Events, *taskResult.event)
			if !worker.recordTelemetry(ctx, *taskResult.event) {
				result.TelemetryFailures++
			}
		}
		if taskResult.err != nil {
			batchErrors = append(batchErrors, taskResult.err)
			if errors.Is(taskResult.err, context.Canceled) ||
				errors.Is(taskResult.err, context.DeadlineExceeded) && ctx.Err() != nil {
				break
			}
		}
	}
	return result, errors.Join(batchErrors...)
}

func (worker *IdentityDeliveryWorker) processClaimedTask(
	ctx context.Context,
	tenantID string,
	projectID string,
	task IdentityDeliveryTask,
) identityDeliveryTaskResult {
	now := worker.nowUTC()
	if err := validateIdentityDeliveryFence(task, now); err != nil {
		return worker.rejectedLeaseResult(err, now)
	}
	if task.TenantID != tenantID || task.ProjectID != projectID {
		return worker.rejectedLeaseResult(ErrIdentityDeliveryScope, now)
	}
	if task.LeaseOwner != worker.leaseOwner {
		return worker.rejectedLeaseResult(ErrIdentityDeliveryLeaseLost, now)
	}
	if err := validateIdentityDeliveryTask(task); err != nil {
		return worker.deadLetterTask(ctx, task, identityDeliveryFailureMalformedTask, false)
	}
	if !task.ChallengeExpiresAt.After(now) {
		return worker.deadLetterTask(ctx, task, identityDeliveryFailureChallengeExpired, true)
	}
	maxAttempts := worker.effectiveMaxAttempts(task)
	if task.Attempt > maxAttempts {
		return worker.deadLetterTask(ctx, task, identityDeliveryFailureAttemptsExhausted, true)
	}

	session, err := worker.startLeaseSession(ctx, task)
	if err != nil {
		if ctxErr := ctx.Err(); ctxErr != nil {
			return identityDeliveryTaskResult{err: ctxErr}
		}
		return worker.rejectedLeaseResult(err, worker.nowUTC())
	}

	leasedTask := session.snapshot()
	vaultCtx, cancel, err := worker.dependencyContext(
		session.workContext(), worker.vaultTimeout, leasedTask.LeaseExpiresAt,
		leasedTask.ChallengeExpiresAt,
	)
	if err != nil {
		if errors.Is(err, errIdentityDeliveryChallengeExpired) {
			return worker.finishExpiredSession(ctx, session)
		}
		_, heartbeatErr, heartbeats := session.stop()
		if heartbeatErr != nil {
			return worker.rejectedLeaseResultWithHeartbeats(heartbeatErr, heartbeats)
		}
		return worker.rejectedLeaseResultWithHeartbeats(err, heartbeats)
	}
	secret, vaultErr := worker.vault.OpenIdentityDelivery(vaultCtx, task.OpaqueRef)
	cancel()
	if vaultErr != nil {
		failureCode := identityDeliveryFailureVaultUnavailable
		if errors.Is(vaultErr, context.DeadlineExceeded) {
			failureCode = identityDeliveryFailureVaultTimeout
		}
		return worker.finishFailedSession(ctx, session, failureCode, maxAttempts)
	}
	if err := validateIdentityDeliverySecret(task, secret); err != nil {
		finalTask, heartbeatErr, heartbeats := session.stop()
		secret = IdentityDeliverySecret{}
		if heartbeatErr != nil {
			return worker.rejectedLeaseResultWithHeartbeats(heartbeatErr, heartbeats)
		}
		if ctxErr := ctx.Err(); ctxErr != nil {
			return identityDeliveryTaskResult{heartbeats: heartbeats, err: ctxErr}
		}
		result := worker.deadLetterTask(
			ctx, finalTask, identityDeliveryFailureMalformedPayload, true,
		)
		result.heartbeats += heartbeats
		return result
	}
	if heartbeatErr := session.failure(); heartbeatErr != nil {
		_, _, heartbeats := session.stop()
		secret = IdentityDeliverySecret{}
		return worker.rejectedLeaseResultWithHeartbeats(heartbeatErr, heartbeats)
	}

	leasedTask = session.snapshot()
	providerCtx, cancel, err := worker.dependencyContext(
		session.workContext(), worker.providerTimeout, leasedTask.LeaseExpiresAt,
		leasedTask.ChallengeExpiresAt,
	)
	if err != nil {
		secret = IdentityDeliverySecret{}
		if errors.Is(err, errIdentityDeliveryChallengeExpired) {
			return worker.finishExpiredSession(ctx, session)
		}
		_, heartbeatErr, heartbeats := session.stop()
		if heartbeatErr != nil {
			return worker.rejectedLeaseResultWithHeartbeats(heartbeatErr, heartbeats)
		}
		return worker.rejectedLeaseResultWithHeartbeats(err, heartbeats)
	}
	delivery := IdentityVerificationDelivery{
		ChallengeID: task.ChallengeID, Channel: task.Channel,
		Destination: secret.Destination, Code: secret.Code,
		Purpose:                canonicalIdentityDeliveryPurpose(task.Purpose),
		ExpiresAt:              task.ChallengeExpiresAt,
		ProviderIdempotencyKey: task.ProviderIdempotencyKey,
	}
	var acceptance IdentityDeliveryProviderAcceptance
	var providerErr error
	if task.Channel == IdentityVerificationEmail {
		acceptance, providerErr = worker.sendIdentityVerification(
			providerCtx, worker.smtp, delivery,
		)
	} else {
		acceptance, providerErr = worker.sendIdentityVerification(
			providerCtx, worker.sms, delivery,
		)
	}
	cancel()
	secret = IdentityDeliverySecret{}
	delivery = IdentityVerificationDelivery{}
	if providerErr != nil {
		failureCode := identityDeliveryFailureSMS
		if task.Channel == IdentityVerificationEmail {
			failureCode = identityDeliveryFailureSMTP
		}
		if errors.Is(providerErr, context.DeadlineExceeded) {
			failureCode = identityDeliveryFailureProviderTimeout
		}
		return worker.finishFailedSession(ctx, session, failureCode, maxAttempts)
	}
	if err := validateIdentityDeliveryProviderAcceptance(
		task, acceptance, worker.nowUTC(),
	); err != nil {
		return worker.finishFailedSession(
			ctx, session, identityDeliveryFailureProviderUnknown, maxAttempts,
		)
	}

	finalTask, heartbeatErr, heartbeats := session.stop()
	if heartbeatErr != nil {
		return worker.rejectedLeaseResultWithHeartbeats(heartbeatErr, heartbeats)
	}
	now = worker.nowUTC()
	if err := validateIdentityDeliveryFence(finalTask, now); err != nil {
		return worker.rejectedLeaseResultWithHeartbeats(err, heartbeats)
	}
	var completionParent context.Context = context.Background()
	if ctx != nil {
		completionParent = context.WithoutCancel(ctx)
	}
	storeCtx, cancel := worker.storeContext(completionParent, finalTask.LeaseExpiresAt, now)
	if cancel == nil {
		return worker.rejectedLeaseResultWithHeartbeats(ErrIdentityDeliveryLeaseExpired, heartbeats)
	}
	err = worker.store.CompleteIdentityDelivery(storeCtx, finalTask, acceptance, now)
	cancel()
	if err != nil {
		if ctxErr := ctx.Err(); ctxErr != nil {
			return identityDeliveryTaskResult{heartbeats: heartbeats, err: ctxErr}
		}
		if identityDeliveryLeaseError(err) {
			return worker.rejectedLeaseResultWithHeartbeats(err, heartbeats)
		}
		return identityDeliveryTaskResult{
			heartbeats: heartbeats,
			err:        fmt.Errorf("complete identity delivery: %w", err),
		}
	}
	event := worker.telemetryEvent(
		IdentityDeliveryEventDelivered, finalTask, maxAttempts, "", 0, now,
	)
	return identityDeliveryTaskResult{
		disposition: identityDeliveryDelivered,
		heartbeats:  heartbeats,
		event:       &event,
	}
}

func (worker *IdentityDeliveryWorker) sendIdentityVerification(
	ctx context.Context,
	adapter IdentityDeliveryAdapter,
	delivery IdentityVerificationDelivery,
) (IdentityDeliveryProviderAcceptance, error) {
	if receiptAdapter, ok := adapter.(IdentityDeliveryAcceptanceAdapter); ok {
		return receiptAdapter.SendIdentityVerificationWithAcceptance(ctx, delivery)
	}
	if err := adapter.SendIdentityVerification(ctx, delivery); err != nil {
		return IdentityDeliveryProviderAcceptance{}, err
	}
	digest := sha256.Sum256([]byte(delivery.ProviderIdempotencyKey))
	return IdentityDeliveryProviderAcceptance{
		Reference:  "provider-ref:legacy/" + hex.EncodeToString(digest[:]),
		AcceptedAt: worker.nowUTC(),
	}, nil
}

func (worker *IdentityDeliveryWorker) finishFailedSession(
	ctx context.Context,
	session *identityDeliveryLeaseSession,
	failureCode string,
	maxAttempts int,
) identityDeliveryTaskResult {
	finalTask, heartbeatErr, heartbeats := session.stop()
	if heartbeatErr != nil {
		return worker.rejectedLeaseResultWithHeartbeats(heartbeatErr, heartbeats)
	}
	if ctxErr := ctx.Err(); ctxErr != nil {
		return identityDeliveryTaskResult{heartbeats: heartbeats, err: ctxErr}
	}
	now := worker.nowUTC()
	if err := validateIdentityDeliveryFence(finalTask, now); err != nil {
		return worker.rejectedLeaseResultWithHeartbeats(err, heartbeats)
	}
	if !finalTask.ChallengeExpiresAt.After(now) {
		result := worker.deadLetterTask(
			ctx, finalTask, identityDeliveryFailureChallengeExpired, true,
		)
		result.heartbeats += heartbeats
		return result
	}
	if finalTask.Attempt >= maxAttempts {
		result := worker.deadLetterTask(ctx, finalTask, failureCode, true)
		result.heartbeats += heartbeats
		return result
	}
	delay := worker.retryDelay(finalTask.Attempt)
	storeCtx, cancel := worker.storeContext(ctx, finalTask.LeaseExpiresAt, now)
	if cancel == nil {
		return worker.rejectedLeaseResultWithHeartbeats(ErrIdentityDeliveryLeaseExpired, heartbeats)
	}
	err := worker.store.RetryIdentityDelivery(
		storeCtx, finalTask, failureCode, now.Add(delay), now,
	)
	cancel()
	if err != nil {
		if ctxErr := ctx.Err(); ctxErr != nil {
			return identityDeliveryTaskResult{heartbeats: heartbeats, err: ctxErr}
		}
		if identityDeliveryLeaseError(err) {
			return worker.rejectedLeaseResultWithHeartbeats(err, heartbeats)
		}
		return identityDeliveryTaskResult{
			heartbeats: heartbeats,
			err:        fmt.Errorf("retry identity delivery: %w", err),
		}
	}
	event := worker.telemetryEvent(
		IdentityDeliveryEventRetryScheduled, finalTask, maxAttempts, failureCode, delay, now,
	)
	return identityDeliveryTaskResult{
		disposition: identityDeliveryRetried,
		heartbeats:  heartbeats,
		event:       &event,
	}
}

func (worker *IdentityDeliveryWorker) finishExpiredSession(
	ctx context.Context,
	session *identityDeliveryLeaseSession,
) identityDeliveryTaskResult {
	finalTask, heartbeatErr, heartbeats := session.stop()
	if heartbeatErr != nil {
		return worker.rejectedLeaseResultWithHeartbeats(heartbeatErr, heartbeats)
	}
	if ctxErr := ctx.Err(); ctxErr != nil {
		return identityDeliveryTaskResult{heartbeats: heartbeats, err: ctxErr}
	}
	result := worker.deadLetterTask(
		ctx, finalTask, identityDeliveryFailureChallengeExpired, true,
	)
	result.heartbeats += heartbeats
	return result
}

func (worker *IdentityDeliveryWorker) deadLetterTask(
	ctx context.Context,
	task IdentityDeliveryTask,
	failureCode string,
	includeTaskMetadata bool,
) identityDeliveryTaskResult {
	now := worker.nowUTC()
	if err := validateIdentityDeliveryFence(task, now); err != nil {
		return worker.rejectedLeaseResult(err, now)
	}
	storeCtx, cancel := worker.storeContext(ctx, task.LeaseExpiresAt, now)
	if cancel == nil {
		return worker.rejectedLeaseResult(ErrIdentityDeliveryLeaseExpired, now)
	}
	err := worker.store.DeadLetterIdentityDelivery(storeCtx, task, failureCode, now)
	cancel()
	if err != nil {
		if ctxErr := ctx.Err(); ctxErr != nil {
			return identityDeliveryTaskResult{err: ctxErr}
		}
		if identityDeliveryLeaseError(err) {
			return worker.rejectedLeaseResult(err, now)
		}
		return identityDeliveryTaskResult{
			err: fmt.Errorf("dead-letter identity delivery: %w", err),
		}
	}
	eventTask := IdentityDeliveryTask{}
	maxAttempts := 0
	if includeTaskMetadata {
		eventTask = task
		maxAttempts = worker.effectiveMaxAttempts(task)
	}
	event := worker.telemetryEvent(
		IdentityDeliveryEventDeadLettered, eventTask, maxAttempts, failureCode, 0, now,
	)
	return identityDeliveryTaskResult{
		disposition: identityDeliveryDeadLettered,
		event:       &event,
	}
}

func (worker *IdentityDeliveryWorker) rejectedLeaseResult(
	err error,
	now time.Time,
) identityDeliveryTaskResult {
	return worker.rejectedLeaseResultWithHeartbeatsAt(err, 0, now)
}

func (worker *IdentityDeliveryWorker) rejectedLeaseResultWithHeartbeats(
	err error,
	heartbeats int,
) identityDeliveryTaskResult {
	return worker.rejectedLeaseResultWithHeartbeatsAt(err, heartbeats, worker.nowUTC())
}

func (worker *IdentityDeliveryWorker) rejectedLeaseResultWithHeartbeatsAt(
	err error,
	heartbeats int,
	now time.Time,
) identityDeliveryTaskResult {
	failureCode := identityDeliveryFailureLeaseLost
	if errors.Is(err, ErrIdentityDeliveryLeaseExpired) {
		failureCode = identityDeliveryFailureLeaseExpired
	}
	event := worker.telemetryEvent(
		IdentityDeliveryEventLeaseRejected, IdentityDeliveryTask{}, 0, failureCode, 0, now,
	)
	return identityDeliveryTaskResult{
		disposition: identityDeliveryLeaseRejected,
		heartbeats:  heartbeats,
		event:       &event,
		err:         err,
	}
}

func (worker *IdentityDeliveryWorker) Redrive(
	ctx context.Context,
	request IdentityDeliveryRedriveRequest,
) (IdentityDeliveryRedriveReceipt, error) {
	if err := validateIdentityDeliveryRedriveRequest(request); err != nil {
		return IdentityDeliveryRedriveReceipt{}, err
	}
	if err := ctx.Err(); err != nil {
		return IdentityDeliveryRedriveReceipt{}, err
	}
	now := worker.nowUTC()
	command := IdentityDeliveryRedriveCommand{
		IdentityDeliveryRedriveRequest: request,
		RequestedAt:                    now,
	}
	storeCtx, cancel := context.WithTimeout(ctx, worker.storeTimeout)
	receipt, err := worker.store.RedriveIdentityDelivery(storeCtx, command)
	cancel()
	if err != nil {
		if ctxErr := ctx.Err(); ctxErr != nil {
			return IdentityDeliveryRedriveReceipt{}, ctxErr
		}
		return IdentityDeliveryRedriveReceipt{}, fmt.Errorf("redrive identity delivery: %w", err)
	}
	if receipt.TaskID != request.TaskID ||
		receipt.LeaseGeneration <= request.ExpectedLeaseGeneration ||
		!validIdentityDeliveryIdentifier(receipt.AuditID) || receipt.RedrivenAt.IsZero() {
		return IdentityDeliveryRedriveReceipt{}, fmt.Errorf("identity delivery redrive receipt is invalid")
	}
	event := worker.telemetryEvent(
		IdentityDeliveryEventRedriven, IdentityDeliveryTask{}, 0, "", 0, now,
	)
	_ = worker.recordTelemetry(ctx, event)
	return receipt, nil
}

func (worker *IdentityDeliveryWorker) Run(
	ctx context.Context,
	options IdentityDeliveryDaemonOptions,
) (result IdentityDeliveryRunResult, err error) {
	result.StartedAt = worker.nowUTC()
	defer func() { result.FinishedAt = worker.nowUTC() }()
	if err := validateIdentityDeliveryScope(options.TenantID, options.ProjectID); err != nil {
		return result, err
	}
	if options.BatchSize == 0 {
		options.BatchSize = 50
	}
	if options.BatchSize < 1 || options.BatchSize > 500 {
		return result, fmt.Errorf("identity delivery daemon batch size must be between 1 and 500")
	}
	if options.PollInterval == 0 {
		options.PollInterval = time.Second
	}
	if options.PollInterval < time.Millisecond || options.PollInterval > time.Minute {
		return result, fmt.Errorf("identity delivery daemon poll interval must be between 1ms and 1m")
	}
	for {
		if ctx.Err() != nil {
			result.GracefulShutdown = true
			return result, nil
		}
		batch, batchErr := worker.ProcessBatch(
			ctx, options.TenantID, options.ProjectID, options.BatchSize,
		)
		result.Batches++
		result.Claimed += batch.Claimed
		result.Delivered += batch.Delivered
		result.Retried += batch.Retried
		result.DeadLettered += batch.DeadLettered
		result.LeaseRejected += batch.LeaseRejected
		result.Heartbeats += batch.Heartbeats
		result.TelemetryFailures += batch.TelemetryFailures
		if ctx.Err() != nil || errors.Is(batchErr, context.Canceled) {
			result.GracefulShutdown = true
			return result, nil
		}
		if batchErr != nil {
			return result, batchErr
		}
		if batch.Claimed != 0 {
			continue
		}
		timer := time.NewTimer(options.PollInterval)
		select {
		case <-ctx.Done():
			if !timer.Stop() {
				select {
				case <-timer.C:
				default:
				}
			}
			result.GracefulShutdown = true
			return result, nil
		case <-timer.C:
		}
	}
}

type identityDeliveryLeaseSession struct {
	worker          *IdentityDeliveryWorker
	mu              sync.RWMutex
	task            IdentityDeliveryTask
	heartbeats      int
	heartbeatErr    error
	workCtx         context.Context
	cancelWork      context.CancelFunc
	heartbeatCtx    context.Context
	cancelHeartbeat context.CancelFunc
	done            chan struct{}
}

func (worker *IdentityDeliveryWorker) startLeaseSession(
	ctx context.Context,
	task IdentityDeliveryTask,
) (*identityDeliveryLeaseSession, error) {
	renewed, err := worker.heartbeat(ctx, task)
	if err != nil {
		return nil, err
	}
	workCtx, cancelWork := context.WithCancel(ctx)
	heartbeatCtx, cancelHeartbeat := context.WithCancel(ctx)
	session := &identityDeliveryLeaseSession{
		worker: worker, task: renewed, heartbeats: 1,
		workCtx: workCtx, cancelWork: cancelWork,
		heartbeatCtx: heartbeatCtx, cancelHeartbeat: cancelHeartbeat,
		done: make(chan struct{}),
	}
	go session.run()
	return session, nil
}

func (session *identityDeliveryLeaseSession) run() {
	defer close(session.done)
	ticker := time.NewTicker(session.worker.heartbeatInterval)
	defer ticker.Stop()
	for {
		select {
		case <-session.heartbeatCtx.Done():
			return
		case <-ticker.C:
			current := session.snapshot()
			renewed, err := session.worker.heartbeat(session.heartbeatCtx, current)
			if err != nil {
				if session.heartbeatCtx.Err() != nil {
					return
				}
				session.mu.Lock()
				session.heartbeatErr = err
				session.mu.Unlock()
				session.cancelWork()
				return
			}
			session.mu.Lock()
			session.task = renewed
			session.heartbeats++
			session.mu.Unlock()
		}
	}
}

func (session *identityDeliveryLeaseSession) snapshot() IdentityDeliveryTask {
	session.mu.RLock()
	defer session.mu.RUnlock()
	return session.task
}

func (session *identityDeliveryLeaseSession) failure() error {
	session.mu.RLock()
	defer session.mu.RUnlock()
	return session.heartbeatErr
}

func (session *identityDeliveryLeaseSession) workContext() context.Context {
	return session.workCtx
}

func (session *identityDeliveryLeaseSession) stop() (IdentityDeliveryTask, error, int) {
	session.cancelHeartbeat()
	<-session.done
	session.cancelWork()
	session.mu.RLock()
	defer session.mu.RUnlock()
	return session.task, session.heartbeatErr, session.heartbeats
}

func (worker *IdentityDeliveryWorker) heartbeat(
	ctx context.Context,
	task IdentityDeliveryTask,
) (IdentityDeliveryTask, error) {
	now := worker.nowUTC()
	if err := validateIdentityDeliveryFence(task, now); err != nil {
		return IdentityDeliveryTask{}, err
	}
	storeCtx, cancel := worker.storeContext(ctx, task.LeaseExpiresAt, now)
	if cancel == nil {
		return IdentityDeliveryTask{}, ErrIdentityDeliveryLeaseExpired
	}
	renewed, err := worker.store.HeartbeatIdentityDelivery(
		storeCtx, task, worker.leaseDuration, now,
	)
	cancel()
	if err != nil {
		if ctxErr := ctx.Err(); ctxErr != nil {
			return IdentityDeliveryTask{}, ctxErr
		}
		return IdentityDeliveryTask{}, fmt.Errorf("identity delivery heartbeat: %w", err)
	}
	if err := validateIdentityDeliveryHeartbeat(task, renewed, worker.nowUTC()); err != nil {
		return IdentityDeliveryTask{}, err
	}
	return renewed, nil
}

func (worker *IdentityDeliveryWorker) dependencyContext(
	parent context.Context,
	timeout time.Duration,
	leaseExpiresAt time.Time,
	challengeExpiresAt time.Time,
) (context.Context, context.CancelFunc, error) {
	now := worker.nowUTC()
	remaining := leaseExpiresAt.Sub(now)
	if remaining <= 0 {
		return nil, nil, ErrIdentityDeliveryLeaseExpired
	}
	if timeout > remaining {
		timeout = remaining
	}
	challengeRemaining := challengeExpiresAt.Sub(now)
	if challengeRemaining <= 0 {
		return nil, nil, errIdentityDeliveryChallengeExpired
	}
	if timeout > challengeRemaining {
		timeout = challengeRemaining
	}
	ctx, cancel := context.WithTimeout(parent, timeout)
	return ctx, cancel, nil
}

func (worker *IdentityDeliveryWorker) storeContext(
	parent context.Context,
	leaseExpiresAt time.Time,
	now time.Time,
) (context.Context, context.CancelFunc) {
	timeout := worker.storeTimeout
	if !leaseExpiresAt.IsZero() {
		remaining := leaseExpiresAt.Sub(now)
		if remaining <= 0 {
			return nil, nil
		}
		if timeout > remaining {
			timeout = remaining
		}
	}
	return context.WithTimeout(parent, timeout)
}

func (worker *IdentityDeliveryWorker) effectiveMaxAttempts(task IdentityDeliveryTask) int {
	if task.MaxAttempts > 0 {
		return task.MaxAttempts
	}
	return worker.maxAttempts
}

func (worker *IdentityDeliveryWorker) retryDelay(attempt int) time.Duration {
	delay := identityDeliveryBackoff(attempt, worker.baseBackoff, worker.maxBackoff)
	delay = worker.jitter(delay)
	if delay < 0 {
		return 0
	}
	if delay > worker.maxBackoff {
		return worker.maxBackoff
	}
	return delay
}

func identityDeliveryBackoff(attempt int, base, maximum time.Duration) time.Duration {
	if attempt <= 1 {
		return base
	}
	delay := base
	for current := 1; current < attempt; current++ {
		if delay >= maximum || delay > maximum/2 {
			return maximum
		}
		delay *= 2
	}
	if delay > maximum {
		return maximum
	}
	return delay
}

func defaultIdentityDeliveryJitter(delay time.Duration) time.Duration {
	if delay <= 1 {
		return delay
	}
	floor := delay / 2
	span := delay - floor
	random, err := cryptorand.Int(cryptorand.Reader, big.NewInt(int64(span)+1))
	if err != nil {
		return delay
	}
	return floor + time.Duration(random.Int64())
}

func (worker *IdentityDeliveryWorker) telemetryEvent(
	eventType string,
	task IdentityDeliveryTask,
	maxAttempts int,
	failureCode string,
	retryDelay time.Duration,
	now time.Time,
) IdentityDeliveryTelemetryEvent {
	event := IdentityDeliveryTelemetryEvent{
		SchemaVersion: IdentityDeliveryTelemetrySchemaVersion,
		Type:          eventType,
		FailureCode:   failureCode,
		OccurredAt:    now,
	}
	if task.Channel == IdentityVerificationEmail || task.Channel == IdentityVerificationPhone {
		event.Channel = task.Channel
		event.Purpose = canonicalIdentityDeliveryPurpose(task.Purpose)
		event.Attempt = task.Attempt
		event.MaxAttempts = maxAttempts
	}
	if retryDelay > 0 {
		event.RetryDelayMS = retryDelay.Milliseconds()
	}
	return event
}

func (worker *IdentityDeliveryWorker) recordTelemetry(
	ctx context.Context,
	event IdentityDeliveryTelemetryEvent,
) bool {
	if worker.telemetry == nil {
		return true
	}
	if !validIdentityDeliveryTelemetryEvent(event) {
		return false
	}
	telemetryCtx, cancel := context.WithTimeout(ctx, worker.telemetryTimeout)
	err := worker.telemetry.RecordIdentityDelivery(telemetryCtx, event)
	cancel()
	return err == nil
}

func validateIdentityDeliveryFence(task IdentityDeliveryTask, now time.Time) error {
	if strings.TrimSpace(task.ID) == "" || strings.TrimSpace(task.TenantID) == "" ||
		strings.TrimSpace(task.ProjectID) == "" || strings.TrimSpace(task.LeaseOwner) == "" {
		return fmt.Errorf("%w: required fence field is empty", ErrIdentityDeliveryLeaseLost)
	}
	if task.LeaseGeneration < 1 {
		return fmt.Errorf("%w: lease generation must be positive", ErrIdentityDeliveryLeaseLost)
	}
	if task.LeaseExpiresAt.IsZero() || !task.LeaseExpiresAt.After(now.UTC()) {
		return ErrIdentityDeliveryLeaseExpired
	}
	return nil
}

func validateIdentityDeliveryTask(task IdentityDeliveryTask) error {
	for _, value := range []string{
		task.ID, task.TenantID, task.ProjectID, task.ChallengeID, task.LeaseOwner,
	} {
		if !validIdentityDeliveryIdentifier(value) {
			return fmt.Errorf("identity delivery identifier is invalid")
		}
	}
	if task.Channel != IdentityVerificationEmail && task.Channel != IdentityVerificationPhone {
		return fmt.Errorf("identity delivery channel is invalid")
	}
	if !validIdentityDeliveryPurpose(task.Purpose) {
		return fmt.Errorf("identity delivery purpose is invalid")
	}
	if !identityDeliveryOpaqueReferencePattern.MatchString(task.OpaqueRef) {
		return fmt.Errorf("identity delivery opaque reference is invalid")
	}
	if !postgresIdentityDeliveryProviderKeyPattern.MatchString(task.ProviderIdempotencyKey) {
		return fmt.Errorf("identity delivery provider idempotency key is invalid")
	}
	if task.ChallengeExpiresAt.IsZero() {
		return fmt.Errorf("identity delivery challenge expiry is required")
	}
	if task.Attempt < 1 || task.MaxAttempts < 0 || task.MaxAttempts > 1000 {
		return fmt.Errorf("identity delivery attempt counters are invalid")
	}
	return nil
}

func validateIdentityDeliveryProviderAcceptance(
	task IdentityDeliveryTask,
	acceptance IdentityDeliveryProviderAcceptance,
	observedAt time.Time,
) error {
	if len(acceptance.Reference) < 1 || len(acceptance.Reference) > 256 ||
		!identityDeliveryProviderAcceptancePattern.MatchString(acceptance.Reference) {
		return errors.New("identity delivery provider acceptance reference is invalid")
	}
	if acceptance.AcceptedAt.IsZero() ||
		!acceptance.AcceptedAt.UTC().Before(task.ChallengeExpiresAt.UTC()) ||
		observedAt.IsZero() || acceptance.AcceptedAt.UTC().After(observedAt.UTC()) {
		return errors.New("identity delivery provider acceptance time is invalid")
	}
	return nil
}

func validateIdentityDeliverySecret(
	task IdentityDeliveryTask,
	secret IdentityDeliverySecret,
) error {
	if secret.TaskID != task.ID || secret.TenantID != task.TenantID ||
		secret.ProjectID != task.ProjectID || secret.ChallengeID != task.ChallengeID ||
		secret.Channel != task.Channel {
		return fmt.Errorf("identity delivery vault binding is invalid")
	}
	if !validIdentityVerificationCode(secret.Code) {
		return fmt.Errorf("identity delivery code is invalid")
	}
	switch task.Channel {
	case IdentityVerificationEmail:
		canonical, err := canonicalSMTPMailbox(secret.Destination)
		if err != nil || canonical != secret.Destination || len(canonical) > 320 {
			return fmt.Errorf("identity delivery email destination is invalid")
		}
	case IdentityVerificationPhone:
		if !validIdentityDeliveryPhone(secret.Destination) {
			return fmt.Errorf("identity delivery phone destination is invalid")
		}
	default:
		return fmt.Errorf("identity delivery channel is invalid")
	}
	return nil
}

func validateIdentityDeliveryHeartbeat(
	previous IdentityDeliveryTask,
	renewed IdentityDeliveryTask,
	now time.Time,
) error {
	if previous.ID != renewed.ID || previous.TenantID != renewed.TenantID ||
		previous.ProjectID != renewed.ProjectID || previous.ChallengeID != renewed.ChallengeID ||
		previous.Channel != renewed.Channel || previous.Purpose != renewed.Purpose ||
		previous.OpaqueRef != renewed.OpaqueRef ||
		previous.ProviderIdempotencyKey != renewed.ProviderIdempotencyKey ||
		!previous.ChallengeExpiresAt.Equal(renewed.ChallengeExpiresAt) ||
		previous.Attempt != renewed.Attempt || previous.MaxAttempts != renewed.MaxAttempts ||
		previous.LeaseOwner != renewed.LeaseOwner ||
		previous.LeaseGeneration != renewed.LeaseGeneration {
		return fmt.Errorf("%w: heartbeat changed fenced task", ErrIdentityDeliveryLeaseLost)
	}
	if renewed.LeaseExpiresAt.Before(previous.LeaseExpiresAt) {
		return fmt.Errorf("%w: heartbeat shortened lease", ErrIdentityDeliveryLeaseLost)
	}
	return validateIdentityDeliveryFence(renewed, now)
}

func validateIdentityDeliveryScope(tenantID, projectID string) error {
	if !validIdentityDeliveryIdentifier(tenantID) || !validIdentityDeliveryIdentifier(projectID) {
		return fmt.Errorf("identity delivery tenant and project scope are invalid")
	}
	return nil
}

func validateIdentityDeliveryRedriveRequest(request IdentityDeliveryRedriveRequest) error {
	if err := validateIdentityDeliveryScope(request.TenantID, request.ProjectID); err != nil {
		return err
	}
	for _, value := range []string{request.TaskID, request.ActorID, request.RequestID} {
		if !validIdentityDeliveryIdentifier(value) {
			return fmt.Errorf("identity delivery redrive audit identity is invalid")
		}
	}
	if request.ExpectedLeaseGeneration < 1 {
		return fmt.Errorf("identity delivery redrive expected generation must be positive")
	}
	if !identityDeliveryReasonPattern.MatchString(request.ReasonCode) {
		return fmt.Errorf("identity delivery redrive reason code is invalid")
	}
	return nil
}

func validIdentityDeliveryTelemetryEvent(event IdentityDeliveryTelemetryEvent) bool {
	if event.SchemaVersion != IdentityDeliveryTelemetrySchemaVersion || event.OccurredAt.IsZero() {
		return false
	}
	switch event.Type {
	case IdentityDeliveryEventDelivered:
		return event.FailureCode == "" && validIdentityDeliveryEventTaskFields(event)
	case IdentityDeliveryEventRetryScheduled:
		return identityDeliveryReasonPattern.MatchString(event.FailureCode) &&
			validIdentityDeliveryEventTaskFields(event) && event.RetryDelayMS >= 0
	case IdentityDeliveryEventDeadLettered:
		return identityDeliveryReasonPattern.MatchString(event.FailureCode)
	case IdentityDeliveryEventLeaseRejected:
		return event.FailureCode == identityDeliveryFailureLeaseExpired ||
			event.FailureCode == identityDeliveryFailureLeaseLost
	case IdentityDeliveryEventRedriven:
		return event.FailureCode == ""
	default:
		return false
	}
}

func validIdentityDeliveryEventTaskFields(event IdentityDeliveryTelemetryEvent) bool {
	return (event.Channel == IdentityVerificationEmail || event.Channel == IdentityVerificationPhone) &&
		validIdentityDeliveryPurpose(event.Purpose) && event.Attempt > 0 &&
		event.MaxAttempts >= event.Attempt
}

func validIdentityDeliveryIdentifier(value string) bool {
	return value == strings.TrimSpace(value) && identityDeliveryIdentifierPattern.MatchString(value)
}

func validIdentityDeliveryPurpose(purpose IdentityVerificationPurpose) bool {
	switch purpose {
	case IdentityVerificationRegistration,
		IdentityVerificationBinding,
		IdentityVerificationLogin,
		IdentityVerificationRecovery,
		IdentityVerificationPurpose("credential_binding"),
		IdentityVerificationPurpose("account_recovery"),
		IdentityVerificationPurpose("step_up"):
		return true
	default:
		return false
	}
}

func canonicalIdentityDeliveryPurpose(
	purpose IdentityVerificationPurpose,
) IdentityVerificationPurpose {
	switch purpose {
	case IdentityVerificationPurpose("credential_binding"):
		return IdentityVerificationBinding
	case IdentityVerificationPurpose("account_recovery"):
		return IdentityVerificationRecovery
	default:
		return purpose
	}
}

func validIdentityDeliveryPhone(value string) bool {
	if len(value) < 9 || len(value) > 16 || value[0] != '+' || value[1] == '0' {
		return false
	}
	for _, character := range value[1:] {
		if character < '0' || character > '9' {
			return false
		}
	}
	return true
}

func identityDeliveryLeaseError(err error) bool {
	return errors.Is(err, ErrIdentityDeliveryLeaseLost) ||
		errors.Is(err, ErrIdentityDeliveryLeaseExpired) ||
		errors.Is(err, ErrIdentityDeliveryScope)
}

func minIdentityDeliveryDuration(left, right time.Duration) time.Duration {
	if left < right {
		return left
	}
	return right
}

func (worker *IdentityDeliveryWorker) nowUTC() time.Time {
	return worker.now().UTC()
}
