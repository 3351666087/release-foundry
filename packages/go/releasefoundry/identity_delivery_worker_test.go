package releasefoundry

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"
)

type identityDeliveryWorkerStore struct {
	mu              sync.Mutex
	tasks           []IdentityDeliveryTask
	claimCalls      int
	heartbeatCalls  int
	completeCalls   int
	retryCalls      int
	deadLetterCalls int
	redriveCalls    int
	heartbeatFn     func(int, IdentityDeliveryTask, time.Duration, time.Time) (IdentityDeliveryTask, error)
	completeErr     error
	retryErr        error
	deadLetterErr   error
	redriveErr      error
	lastCompleted   IdentityDeliveryTask
	lastAcceptance  IdentityDeliveryProviderAcceptance
	lastRetried     IdentityDeliveryTask
	lastRetryCode   string
	lastRetryAt     time.Time
	lastDeadLetter  IdentityDeliveryTask
	lastDeadCode    string
	lastRedrive     IdentityDeliveryRedriveCommand
	redriveReceipt  IdentityDeliveryRedriveReceipt
	heartbeatSignal chan struct{}
}

func (store *identityDeliveryWorkerStore) ClaimIdentityDeliveries(
	_ context.Context,
	_ string,
	_ string,
	_ string,
	_ int,
	_ time.Duration,
	_ time.Time,
) ([]IdentityDeliveryTask, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	store.claimCalls++
	if store.claimCalls > 1 {
		return nil, nil
	}
	return append([]IdentityDeliveryTask(nil), store.tasks...), nil
}

func (store *identityDeliveryWorkerStore) HeartbeatIdentityDelivery(
	_ context.Context,
	task IdentityDeliveryTask,
	duration time.Duration,
	now time.Time,
) (IdentityDeliveryTask, error) {
	store.mu.Lock()
	store.heartbeatCalls++
	call := store.heartbeatCalls
	fn := store.heartbeatFn
	signal := store.heartbeatSignal
	store.mu.Unlock()

	if signal != nil {
		select {
		case signal <- struct{}{}:
		default:
		}
	}
	if fn != nil {
		return fn(call, task, duration, now)
	}
	task.LeaseExpiresAt = task.LeaseExpiresAt.Add(duration)
	return task, nil
}

func (store *identityDeliveryWorkerStore) CompleteIdentityDelivery(
	_ context.Context,
	task IdentityDeliveryTask,
	acceptance IdentityDeliveryProviderAcceptance,
	_ time.Time,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	store.completeCalls++
	store.lastCompleted = task
	store.lastAcceptance = acceptance
	return store.completeErr
}

func (store *identityDeliveryWorkerStore) RetryIdentityDelivery(
	_ context.Context,
	task IdentityDeliveryTask,
	failureCode string,
	nextAttemptAt time.Time,
	_ time.Time,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	store.retryCalls++
	store.lastRetried = task
	store.lastRetryCode = failureCode
	store.lastRetryAt = nextAttemptAt
	return store.retryErr
}

func (store *identityDeliveryWorkerStore) DeadLetterIdentityDelivery(
	_ context.Context,
	task IdentityDeliveryTask,
	failureCode string,
	_ time.Time,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	store.deadLetterCalls++
	store.lastDeadLetter = task
	store.lastDeadCode = failureCode
	return store.deadLetterErr
}

func (store *identityDeliveryWorkerStore) RedriveIdentityDelivery(
	_ context.Context,
	command IdentityDeliveryRedriveCommand,
) (IdentityDeliveryRedriveReceipt, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	store.redriveCalls++
	store.lastRedrive = command
	if store.redriveErr != nil {
		return IdentityDeliveryRedriveReceipt{}, store.redriveErr
	}
	if store.redriveReceipt.TaskID != "" {
		return store.redriveReceipt, nil
	}
	return IdentityDeliveryRedriveReceipt{
		TaskID: command.TaskID, LeaseGeneration: command.ExpectedLeaseGeneration + 1,
		AuditID: "audit-1", RedrivenAt: command.RequestedAt,
	}, nil
}

func (store *identityDeliveryWorkerStore) counts() (int, int, int, int, int, int) {
	store.mu.Lock()
	defer store.mu.Unlock()
	return store.claimCalls, store.heartbeatCalls, store.completeCalls,
		store.retryCalls, store.deadLetterCalls, store.redriveCalls
}

func (store *identityDeliveryWorkerStore) retrySnapshot() (string, time.Time) {
	store.mu.Lock()
	defer store.mu.Unlock()
	return store.lastRetryCode, store.lastRetryAt
}

func (store *identityDeliveryWorkerStore) deadSnapshot() string {
	store.mu.Lock()
	defer store.mu.Unlock()
	return store.lastDeadCode
}

func (store *identityDeliveryWorkerStore) redriveSnapshot() IdentityDeliveryRedriveCommand {
	store.mu.Lock()
	defer store.mu.Unlock()
	return store.lastRedrive
}

type identityDeliveryWorkerVault struct {
	mu          sync.Mutex
	secret      IdentityDeliverySecret
	err         error
	openFn      func(context.Context, string) (IdentityDeliverySecret, error)
	calls       int
	hadDeadline bool
}

func (vault *identityDeliveryWorkerVault) OpenIdentityDelivery(
	ctx context.Context,
	ref string,
) (IdentityDeliverySecret, error) {
	vault.mu.Lock()
	vault.calls++
	_, vault.hadDeadline = ctx.Deadline()
	fn := vault.openFn
	secret := vault.secret
	err := vault.err
	vault.mu.Unlock()
	if fn != nil {
		return fn(ctx, ref)
	}
	return secret, err
}

func (vault *identityDeliveryWorkerVault) snapshot() (int, bool) {
	vault.mu.Lock()
	defer vault.mu.Unlock()
	return vault.calls, vault.hadDeadline
}

type identityDeliveryWorkerAdapter struct {
	mu           sync.Mutex
	calls        int
	deliveries   []IdentityVerificationDelivery
	hadDeadline  bool
	sendFn       func(context.Context, IdentityVerificationDelivery) error
	acceptanceFn func(context.Context, IdentityVerificationDelivery) (IdentityDeliveryProviderAcceptance, error)
	started      chan struct{}
	startOnce    sync.Once
}

func (adapter *identityDeliveryWorkerAdapter) SendIdentityVerificationWithAcceptance(
	ctx context.Context,
	delivery IdentityVerificationDelivery,
) (IdentityDeliveryProviderAcceptance, error) {
	adapter.mu.Lock()
	fn := adapter.acceptanceFn
	adapter.mu.Unlock()
	if fn != nil {
		return fn(ctx, delivery)
	}
	err := adapter.SendIdentityVerification(ctx, delivery)
	if err != nil {
		return IdentityDeliveryProviderAcceptance{}, err
	}
	return IdentityDeliveryProviderAcceptance{
		Reference:  "provider-ref:test-1",
		AcceptedAt: identityDeliveryTestNow(),
	}, nil
}

func (adapter *identityDeliveryWorkerAdapter) SendIdentityVerification(
	ctx context.Context,
	delivery IdentityVerificationDelivery,
) error {
	adapter.mu.Lock()
	adapter.calls++
	adapter.deliveries = append(adapter.deliveries, delivery)
	_, adapter.hadDeadline = ctx.Deadline()
	fn := adapter.sendFn
	started := adapter.started
	adapter.mu.Unlock()
	if started != nil {
		adapter.startOnce.Do(func() { close(started) })
	}
	if fn != nil {
		return fn(ctx, delivery)
	}
	return nil
}

func (adapter *identityDeliveryWorkerAdapter) snapshot() (
	int,
	bool,
	[]IdentityVerificationDelivery,
) {
	adapter.mu.Lock()
	defer adapter.mu.Unlock()
	return adapter.calls, adapter.hadDeadline,
		append([]IdentityVerificationDelivery(nil), adapter.deliveries...)
}

type identityDeliveryWorkerTelemetry struct {
	mu     sync.Mutex
	events []IdentityDeliveryTelemetryEvent
	err    error
}

func (telemetry *identityDeliveryWorkerTelemetry) RecordIdentityDelivery(
	_ context.Context,
	event IdentityDeliveryTelemetryEvent,
) error {
	telemetry.mu.Lock()
	defer telemetry.mu.Unlock()
	telemetry.events = append(telemetry.events, event)
	return telemetry.err
}

func (telemetry *identityDeliveryWorkerTelemetry) snapshot() []IdentityDeliveryTelemetryEvent {
	telemetry.mu.Lock()
	defer telemetry.mu.Unlock()
	return append([]IdentityDeliveryTelemetryEvent(nil), telemetry.events...)
}

func identityDeliveryTestNow() time.Time {
	return time.Date(2026, 7, 11, 8, 0, 0, 0, time.UTC)
}

func identityDeliveryTestTask() IdentityDeliveryTask {
	now := identityDeliveryTestNow()
	return IdentityDeliveryTask{
		ID: "delivery-1", TenantID: "tenant-1", ProjectID: "project-1",
		ChallengeID: "ivc_challenge-1", Channel: IdentityVerificationEmail,
		Purpose: IdentityVerificationLogin, OpaqueRef: "vault:identity-delivery-1",
		ChallengeExpiresAt: now.Add(10 * time.Minute), Attempt: 1, MaxAttempts: 3,
		ProviderIdempotencyKey: "identity-delivery:challenge-1:0",
		LeaseOwner:             "delivery-worker-1", LeaseGeneration: 7,
		LeaseExpiresAt: now.Add(300 * time.Millisecond),
	}
}

func identityDeliveryTestSecret(task IdentityDeliveryTask) IdentityDeliverySecret {
	destination := "person@example.com"
	if task.Channel == IdentityVerificationPhone {
		destination = "+8613812345678"
	}
	return IdentityDeliverySecret{
		TaskID: task.ID, TenantID: task.TenantID, ProjectID: task.ProjectID,
		ChallengeID: task.ChallengeID, Channel: task.Channel,
		Destination: destination, Code: "123456",
	}
}

func newIdentityDeliveryTestWorker(
	t *testing.T,
	store *identityDeliveryWorkerStore,
	vault *identityDeliveryWorkerVault,
	smtp *identityDeliveryWorkerAdapter,
	sms *identityDeliveryWorkerAdapter,
	telemetry IdentityDeliveryTelemetry,
	customize func(*IdentityDeliveryWorkerOptions),
) *IdentityDeliveryWorker {
	t.Helper()
	options := IdentityDeliveryWorkerOptions{
		Store: store, Vault: vault, SMTP: smtp, SMS: sms, Telemetry: telemetry,
		LeaseOwner: "delivery-worker-1", LeaseDuration: 300 * time.Millisecond,
		HeartbeatInterval: 20 * time.Millisecond, ProviderTimeout: 120 * time.Millisecond,
		VaultTimeout: 60 * time.Millisecond, StoreTimeout: 60 * time.Millisecond,
		TelemetryTimeout: 30 * time.Millisecond, BaseBackoff: 10 * time.Millisecond,
		MaxBackoff: time.Second, MaxAttempts: 4,
		Jitter: func(delay time.Duration) time.Duration { return delay },
		Now:    identityDeliveryTestNow,
	}
	if customize != nil {
		customize(&options)
	}
	worker, err := NewIdentityDeliveryWorker(options)
	if err != nil {
		t.Fatal(err)
	}
	return worker
}

func TestIdentityDeliveryWorkerCompletesEmailWithFencedHeartbeatAndDeadlines(t *testing.T) {
	task := identityDeliveryTestTask()
	store := &identityDeliveryWorkerStore{tasks: []IdentityDeliveryTask{task}}
	vault := &identityDeliveryWorkerVault{secret: identityDeliveryTestSecret(task)}
	smtp := &identityDeliveryWorkerAdapter{}
	sms := &identityDeliveryWorkerAdapter{}
	telemetry := &identityDeliveryWorkerTelemetry{}

	result, err := newIdentityDeliveryTestWorker(
		t, store, vault, smtp, sms, telemetry, nil,
	).ProcessBatch(context.Background(), task.TenantID, task.ProjectID, 10)
	if err != nil {
		t.Fatal(err)
	}
	_, heartbeats, completed, retried, dead, _ := store.counts()
	if result.Delivered != 1 || result.Claimed != 1 || result.Heartbeats != 1 ||
		heartbeats != 1 || completed != 1 || retried != 0 || dead != 0 {
		t.Fatalf("unexpected delivery result: result=%#v counts=%d/%d/%d/%d", result, heartbeats, completed, retried, dead)
	}
	vaultCalls, vaultDeadline := vault.snapshot()
	smtpCalls, smtpDeadline, deliveries := smtp.snapshot()
	smsCalls, _, _ := sms.snapshot()
	if vaultCalls != 1 || !vaultDeadline || smtpCalls != 1 || !smtpDeadline || smsCalls != 0 {
		t.Fatalf("dependencies were not deadline-bounded and routed: vault=%d/%v smtp=%d/%v sms=%d", vaultCalls, vaultDeadline, smtpCalls, smtpDeadline, smsCalls)
	}
	if len(deliveries) != 1 || deliveries[0].Destination != "person@example.com" ||
		deliveries[0].Code != "123456" || deliveries[0].ChallengeID != task.ChallengeID ||
		deliveries[0].ProviderIdempotencyKey != task.ProviderIdempotencyKey {
		t.Fatalf("unexpected adapter payload: %#v", deliveries)
	}
	if store.lastCompleted.ProviderIdempotencyKey != task.ProviderIdempotencyKey ||
		store.lastAcceptance.Reference != "provider-ref:test-1" ||
		!store.lastAcceptance.AcceptedAt.Equal(identityDeliveryTestNow()) {
		t.Fatalf("provider acceptance was not persisted: %#v", store.lastAcceptance)
	}
	events := telemetry.snapshot()
	if len(events) != 1 || events[0].Type != IdentityDeliveryEventDelivered ||
		events[0].FailureCode != "" {
		t.Fatalf("unexpected telemetry: %#v", events)
	}
}

func TestIdentityDeliveryWorkerCommitsAcceptanceRecordedBeforeChallengeExpiry(t *testing.T) {
	base := identityDeliveryTestNow()
	clock := &verificationClock{now: base}
	task := identityDeliveryTestTask()
	task.ChallengeExpiresAt = base.Add(2 * time.Minute)
	task.LeaseExpiresAt = base.Add(10 * time.Minute)
	store := &identityDeliveryWorkerStore{tasks: []IdentityDeliveryTask{task}}
	vault := &identityDeliveryWorkerVault{secret: identityDeliveryTestSecret(task)}
	smtp := &identityDeliveryWorkerAdapter{
		acceptanceFn: func(
			_ context.Context,
			delivery IdentityVerificationDelivery,
		) (IdentityDeliveryProviderAcceptance, error) {
			if delivery.ProviderIdempotencyKey != task.ProviderIdempotencyKey {
				t.Fatal("provider idempotency key changed at adapter boundary")
			}
			clock.Add(3 * time.Minute)
			return IdentityDeliveryProviderAcceptance{
				Reference:  "provider-ref:before-expiry",
				AcceptedAt: base.Add(time.Minute),
			}, nil
		},
	}
	sms := &identityDeliveryWorkerAdapter{}

	result, err := newIdentityDeliveryTestWorker(
		t, store, vault, smtp, sms, nil,
		func(options *IdentityDeliveryWorkerOptions) { options.Now = clock.Now },
	).ProcessBatch(context.Background(), task.TenantID, task.ProjectID, 1)
	if err != nil {
		t.Fatal(err)
	}
	_, _, completeCalls, retryCalls, deadCalls, _ := store.counts()
	if result.Delivered != 1 || completeCalls != 1 || retryCalls != 0 || deadCalls != 0 ||
		store.lastAcceptance.Reference != "provider-ref:before-expiry" {
		t.Fatalf("accepted delivery was not committed after challenge expiry: result=%#v", result)
	}
}

func TestIdentityDeliveryWorkerRetriesUnknownAcceptanceWithSameProviderKey(t *testing.T) {
	task := identityDeliveryTestTask()
	store := &identityDeliveryWorkerStore{tasks: []IdentityDeliveryTask{task}}
	vault := &identityDeliveryWorkerVault{secret: identityDeliveryTestSecret(task)}
	var observedProviderKey string
	smtp := &identityDeliveryWorkerAdapter{
		acceptanceFn: func(
			_ context.Context,
			delivery IdentityVerificationDelivery,
		) (IdentityDeliveryProviderAcceptance, error) {
			observedProviderKey = delivery.ProviderIdempotencyKey
			return IdentityDeliveryProviderAcceptance{
				Reference:  "unsafe acceptance reference with spaces",
				AcceptedAt: identityDeliveryTestNow().Add(time.Second),
			}, nil
		},
	}
	sms := &identityDeliveryWorkerAdapter{}

	result, err := newIdentityDeliveryTestWorker(
		t, store, vault, smtp, sms, nil, nil,
	).ProcessBatch(context.Background(), task.TenantID, task.ProjectID, 1)
	if err != nil {
		t.Fatal(err)
	}
	_, _, completeCalls, retryCalls, deadCalls, _ := store.counts()
	if result.Retried != 1 || completeCalls != 0 || retryCalls != 1 || deadCalls != 0 ||
		observedProviderKey != task.ProviderIdempotencyKey ||
		store.lastRetried.ProviderIdempotencyKey != task.ProviderIdempotencyKey ||
		store.lastRetryCode != identityDeliveryFailureProviderUnknown {
		t.Fatalf("unknown provider outcome did not preserve idempotency: result=%#v", result)
	}
}

func TestIdentityDeliveryWorkerRejectsMalformedTaskBeforeVaultOrAdapter(t *testing.T) {
	task := identityDeliveryTestTask()
	task.OpaqueRef = "vault:token=123456"
	store := &identityDeliveryWorkerStore{tasks: []IdentityDeliveryTask{task}}
	vault := &identityDeliveryWorkerVault{secret: identityDeliveryTestSecret(task)}
	smtp := &identityDeliveryWorkerAdapter{}
	sms := &identityDeliveryWorkerAdapter{}

	result, err := newIdentityDeliveryTestWorker(
		t, store, vault, smtp, sms, nil, nil,
	).ProcessBatch(context.Background(), task.TenantID, task.ProjectID, 10)
	if err != nil {
		t.Fatal(err)
	}
	_, heartbeats, completed, retried, dead, _ := store.counts()
	vaultCalls, _ := vault.snapshot()
	smtpCalls, _, _ := smtp.snapshot()
	if result.DeadLettered != 1 || dead != 1 || store.deadSnapshot() != identityDeliveryFailureMalformedTask ||
		heartbeats != 0 || completed != 0 || retried != 0 || vaultCalls != 0 || smtpCalls != 0 {
		t.Fatalf("malformed task reached a dependency: result=%#v counts=%d/%d/%d/%d vault=%d smtp=%d", result, heartbeats, completed, retried, dead, vaultCalls, smtpCalls)
	}
	serialized := fmt.Sprintf("%#v", result.Events)
	if strings.Contains(serialized, "123456") || strings.Contains(serialized, "raw-code") {
		t.Fatalf("malformed task leaked into telemetry: %s", serialized)
	}
}

func TestIdentityDeliveryWorkerRejectsExpiredLeaseWithoutTransition(t *testing.T) {
	task := identityDeliveryTestTask()
	task.LeaseExpiresAt = identityDeliveryTestNow()
	store := &identityDeliveryWorkerStore{tasks: []IdentityDeliveryTask{task}}
	vault := &identityDeliveryWorkerVault{secret: identityDeliveryTestSecret(task)}
	smtp := &identityDeliveryWorkerAdapter{}
	sms := &identityDeliveryWorkerAdapter{}

	result, err := newIdentityDeliveryTestWorker(
		t, store, vault, smtp, sms, nil, nil,
	).ProcessBatch(context.Background(), task.TenantID, task.ProjectID, 10)
	if !errors.Is(err, ErrIdentityDeliveryLeaseExpired) || result.LeaseRejected != 1 {
		t.Fatalf("expired lease was not rejected: result=%#v err=%v", result, err)
	}
	_, heartbeats, completed, retried, dead, _ := store.counts()
	vaultCalls, _ := vault.snapshot()
	if heartbeats != 0 || completed != 0 || retried != 0 || dead != 0 || vaultCalls != 0 {
		t.Fatalf("expired lease caused side effects: hb=%d complete=%d retry=%d dead=%d vault=%d", heartbeats, completed, retried, dead, vaultCalls)
	}
}

func TestIdentityDeliveryWorkerDeadLettersExpiredChallengeBeforeVault(t *testing.T) {
	task := identityDeliveryTestTask()
	task.ChallengeExpiresAt = identityDeliveryTestNow()
	store := &identityDeliveryWorkerStore{tasks: taskSlice(task)}
	vault := &identityDeliveryWorkerVault{secret: identityDeliveryTestSecret(task)}
	smtp := &identityDeliveryWorkerAdapter{}
	sms := &identityDeliveryWorkerAdapter{}

	result, err := newIdentityDeliveryTestWorker(
		t, store, vault, smtp, sms, nil, nil,
	).ProcessBatch(context.Background(), task.TenantID, task.ProjectID, 10)
	if err != nil {
		t.Fatal(err)
	}
	vaultCalls, _ := vault.snapshot()
	_, heartbeats, completed, retried, dead, _ := store.counts()
	if result.DeadLettered != 1 || store.deadSnapshot() != identityDeliveryFailureChallengeExpired ||
		vaultCalls != 0 || heartbeats != 0 || completed != 0 || retried != 0 || dead != 1 {
		t.Fatalf("expired challenge was not rejected before vault: result=%#v vault=%d hb=%d complete=%d retry=%d dead=%d", result, vaultCalls, heartbeats, completed, retried, dead)
	}
}

func TestIdentityDeliveryWorkerRejectsCrossScopeClaimBeforeSideEffects(t *testing.T) {
	task := identityDeliveryTestTask()
	store := &identityDeliveryWorkerStore{tasks: []IdentityDeliveryTask{task}}
	vault := &identityDeliveryWorkerVault{secret: identityDeliveryTestSecret(task)}
	smtp := &identityDeliveryWorkerAdapter{}
	sms := &identityDeliveryWorkerAdapter{}

	result, err := newIdentityDeliveryTestWorker(
		t, store, vault, smtp, sms, nil, nil,
	).ProcessBatch(context.Background(), "tenant-other", task.ProjectID, 10)
	if !errors.Is(err, ErrIdentityDeliveryScope) || result.LeaseRejected != 1 {
		t.Fatalf("cross-scope claim was not rejected: result=%#v err=%v", result, err)
	}
	_, heartbeats, completed, retried, dead, _ := store.counts()
	vaultCalls, _ := vault.snapshot()
	if heartbeats+completed+retried+dead+vaultCalls != 0 {
		t.Fatalf("cross-scope claim caused side effects: %d/%d/%d/%d/%d", heartbeats, completed, retried, dead, vaultCalls)
	}
}

func TestIdentityDeliveryWorkerRejectsHeartbeatGenerationMutation(t *testing.T) {
	task := identityDeliveryTestTask()
	store := &identityDeliveryWorkerStore{
		tasks: []IdentityDeliveryTask{task},
		heartbeatFn: func(
			_ int,
			leased IdentityDeliveryTask,
			_ time.Duration,
			_ time.Time,
		) (IdentityDeliveryTask, error) {
			leased.LeaseGeneration++
			leased.LeaseExpiresAt = leased.LeaseExpiresAt.Add(time.Second)
			return leased, nil
		},
	}
	vault := &identityDeliveryWorkerVault{secret: identityDeliveryTestSecret(task)}
	smtp := &identityDeliveryWorkerAdapter{}
	sms := &identityDeliveryWorkerAdapter{}

	result, err := newIdentityDeliveryTestWorker(
		t, store, vault, smtp, sms, nil, nil,
	).ProcessBatch(context.Background(), task.TenantID, task.ProjectID, 10)
	if !errors.Is(err, ErrIdentityDeliveryLeaseLost) || result.LeaseRejected != 1 {
		t.Fatalf("generation mutation was not fenced: result=%#v err=%v", result, err)
	}
	_, heartbeats, completed, retried, dead, _ := store.counts()
	vaultCalls, _ := vault.snapshot()
	if heartbeats != 1 || completed != 0 || retried != 0 || dead != 0 || vaultCalls != 0 {
		t.Fatalf("fenced generation reached a dependency: hb=%d complete=%d retry=%d dead=%d vault=%d", heartbeats, completed, retried, dead, vaultCalls)
	}
}

func TestIdentityDeliveryWorkerHeartbeatsWhileProviderIsBlocked(t *testing.T) {
	task := identityDeliveryTestTask()
	signal := make(chan struct{}, 16)
	store := &identityDeliveryWorkerStore{
		tasks: taskSlice(task), heartbeatSignal: signal,
	}
	vault := &identityDeliveryWorkerVault{secret: identityDeliveryTestSecret(task)}
	smtp := &identityDeliveryWorkerAdapter{
		sendFn: func(ctx context.Context, _ IdentityVerificationDelivery) error {
			for {
				_, heartbeats, _, _, _, _ := store.counts()
				if heartbeats >= 3 {
					return nil
				}
				select {
				case <-ctx.Done():
					return ctx.Err()
				case <-signal:
				}
			}
		},
	}
	sms := &identityDeliveryWorkerAdapter{}

	result, err := newIdentityDeliveryTestWorker(
		t, store, vault, smtp, sms, nil, nil,
	).ProcessBatch(context.Background(), task.TenantID, task.ProjectID, 10)
	if err != nil {
		t.Fatal(err)
	}
	_, heartbeats, completed, _, _, _ := store.counts()
	if result.Delivered != 1 || result.Heartbeats < 3 || heartbeats < 3 || completed != 1 {
		t.Fatalf("provider was not protected by heartbeat: result=%#v heartbeats=%d complete=%d", result, heartbeats, completed)
	}
	store.mu.Lock()
	completedGeneration := store.lastCompleted.LeaseGeneration
	completedExpiry := store.lastCompleted.LeaseExpiresAt
	store.mu.Unlock()
	if completedGeneration != task.LeaseGeneration || !completedExpiry.After(task.LeaseExpiresAt) {
		t.Fatalf("completion did not preserve refreshed fence: generation=%d expiry=%s", completedGeneration, completedExpiry)
	}
}

func TestIdentityDeliveryWorkerRoutesPhoneOnlyToSMSAdapter(t *testing.T) {
	task := identityDeliveryTestTask()
	task.Channel = IdentityVerificationPhone
	store := &identityDeliveryWorkerStore{tasks: taskSlice(task)}
	vault := &identityDeliveryWorkerVault{secret: identityDeliveryTestSecret(task)}
	smtp := &identityDeliveryWorkerAdapter{}
	sms := &identityDeliveryWorkerAdapter{}

	result, err := newIdentityDeliveryTestWorker(
		t, store, vault, smtp, sms, nil, nil,
	).ProcessBatch(context.Background(), task.TenantID, task.ProjectID, 10)
	if err != nil {
		t.Fatal(err)
	}
	smtpCalls, _, _ := smtp.snapshot()
	smsCalls, smsDeadline, deliveries := sms.snapshot()
	if result.Delivered != 1 || smtpCalls != 0 || smsCalls != 1 || !smsDeadline ||
		len(deliveries) != 1 || deliveries[0].Destination != "+8613812345678" {
		t.Fatalf("phone delivery was not isolated to SMS: result=%#v smtp=%d sms=%d/%v deliveries=%#v", result, smtpCalls, smsCalls, smsDeadline, deliveries)
	}
}

func TestIdentityDeliveryWorkerCancelsProviderWhenHeartbeatLosesFence(t *testing.T) {
	task := identityDeliveryTestTask()
	store := &identityDeliveryWorkerStore{
		tasks: taskSlice(task),
		heartbeatFn: func(
			call int,
			leased IdentityDeliveryTask,
			duration time.Duration,
			_ time.Time,
		) (IdentityDeliveryTask, error) {
			if call >= 2 {
				return IdentityDeliveryTask{}, ErrIdentityDeliveryLeaseLost
			}
			leased.LeaseExpiresAt = leased.LeaseExpiresAt.Add(duration)
			return leased, nil
		},
	}
	vault := &identityDeliveryWorkerVault{secret: identityDeliveryTestSecret(task)}
	providerCanceled := make(chan struct{})
	smtp := &identityDeliveryWorkerAdapter{
		sendFn: func(ctx context.Context, _ IdentityVerificationDelivery) error {
			<-ctx.Done()
			close(providerCanceled)
			return ctx.Err()
		},
	}
	sms := &identityDeliveryWorkerAdapter{}

	result, err := newIdentityDeliveryTestWorker(
		t, store, vault, smtp, sms, nil, nil,
	).ProcessBatch(context.Background(), task.TenantID, task.ProjectID, 10)
	if !errors.Is(err, ErrIdentityDeliveryLeaseLost) || result.LeaseRejected != 1 {
		t.Fatalf("heartbeat fence loss did not reject delivery: result=%#v err=%v", result, err)
	}
	select {
	case <-providerCanceled:
	default:
		t.Fatal("provider context was not canceled after heartbeat fence loss")
	}
	_, heartbeats, completed, retried, dead, _ := store.counts()
	if heartbeats < 2 || completed != 0 || retried != 0 || dead != 0 {
		t.Fatalf("fence loss caused a terminal transition: hb=%d complete=%d retry=%d dead=%d", heartbeats, completed, retried, dead)
	}
}

func TestIdentityDeliveryWorkerBoundsProviderAndSchedulesInjectedJitter(t *testing.T) {
	task := identityDeliveryTestTask()
	task.Attempt = 3
	task.MaxAttempts = 5
	store := &identityDeliveryWorkerStore{tasks: taskSlice(task)}
	vault := &identityDeliveryWorkerVault{secret: identityDeliveryTestSecret(task)}
	smtp := &identityDeliveryWorkerAdapter{
		sendFn: func(ctx context.Context, _ IdentityVerificationDelivery) error {
			<-ctx.Done()
			return ctx.Err()
		},
	}
	sms := &identityDeliveryWorkerAdapter{}
	started := time.Now()
	result, err := newIdentityDeliveryTestWorker(
		t, store, vault, smtp, sms, nil,
		func(options *IdentityDeliveryWorkerOptions) {
			options.ProviderTimeout = 15 * time.Millisecond
			options.Jitter = func(delay time.Duration) time.Duration { return delay / 2 }
		},
	).ProcessBatch(context.Background(), task.TenantID, task.ProjectID, 10)
	if err != nil {
		t.Fatal(err)
	}
	if elapsed := time.Since(started); elapsed > 150*time.Millisecond {
		t.Fatalf("provider deadline was not bounded: %s", elapsed)
	}
	code, retryAt := store.retrySnapshot()
	expectedDelay := 20 * time.Millisecond
	if result.Retried != 1 || code != identityDeliveryFailureProviderTimeout ||
		!retryAt.Equal(identityDeliveryTestNow().Add(expectedDelay)) {
		t.Fatalf("unexpected retry: result=%#v code=%q retry_at=%s", result, code, retryAt)
	}
	if len(result.Events) != 1 || result.Events[0].RetryDelayMS != expectedDelay.Milliseconds() {
		t.Fatalf("retry telemetry did not use injected jitter: %#v", result.Events)
	}
}

func TestIdentityDeliveryWorkerDoesNotRetryChallengeThatExpiresDuringProvider(t *testing.T) {
	now := time.Now().UTC()
	task := identityDeliveryTestTask()
	task.ChallengeExpiresAt = now.Add(25 * time.Millisecond)
	task.LeaseExpiresAt = now.Add(300 * time.Millisecond)
	store := &identityDeliveryWorkerStore{tasks: taskSlice(task)}
	vault := &identityDeliveryWorkerVault{secret: identityDeliveryTestSecret(task)}
	smtp := &identityDeliveryWorkerAdapter{
		sendFn: func(ctx context.Context, _ IdentityVerificationDelivery) error {
			<-ctx.Done()
			return ctx.Err()
		},
	}
	sms := &identityDeliveryWorkerAdapter{}

	result, err := newIdentityDeliveryTestWorker(
		t, store, vault, smtp, sms, nil,
		func(options *IdentityDeliveryWorkerOptions) {
			options.Now = time.Now
		},
	).ProcessBatch(context.Background(), task.TenantID, task.ProjectID, 10)
	if err != nil {
		t.Fatal(err)
	}
	_, _, completed, retried, dead, _ := store.counts()
	if result.DeadLettered != 1 || completed != 0 || retried != 0 || dead != 1 ||
		store.deadSnapshot() != identityDeliveryFailureChallengeExpired {
		t.Fatalf("expired in-flight challenge was retried: result=%#v complete=%d retry=%d dead=%d code=%q", result, completed, retried, dead, store.deadSnapshot())
	}
}

func TestIdentityDeliveryWorkerDeadLettersFinalProviderFailureWithRedactedTelemetry(t *testing.T) {
	task := identityDeliveryTestTask()
	task.Attempt = 3
	task.MaxAttempts = 3
	store := &identityDeliveryWorkerStore{tasks: taskSlice(task)}
	vault := &identityDeliveryWorkerVault{secret: identityDeliveryTestSecret(task)}
	smtp := &identityDeliveryWorkerAdapter{
		sendFn: func(context.Context, IdentityVerificationDelivery) error {
			return errors.New("smtp rejected token=otp-secret destination=person@example.com")
		},
	}
	sms := &identityDeliveryWorkerAdapter{}
	telemetry := &identityDeliveryWorkerTelemetry{}

	result, err := newIdentityDeliveryTestWorker(
		t, store, vault, smtp, sms, telemetry, nil,
	).ProcessBatch(context.Background(), task.TenantID, task.ProjectID, 10)
	if err != nil {
		t.Fatal(err)
	}
	_, _, completed, retried, dead, _ := store.counts()
	if result.DeadLettered != 1 || dead != 1 || retried != 0 || completed != 0 ||
		store.deadSnapshot() != identityDeliveryFailureSMTP {
		t.Fatalf("final attempt did not dead-letter: result=%#v complete=%d retry=%d dead=%d", result, completed, retried, dead)
	}
	serialized := strings.ToLower(fmt.Sprintf("%#v", telemetry.snapshot()))
	for _, forbidden := range []string{"otp-secret", "person@example.com", "token=", "destination="} {
		if strings.Contains(serialized, forbidden) {
			t.Fatalf("telemetry leaked %q: %s", forbidden, serialized)
		}
	}
}

func TestIdentityDeliveryWorkerDeadLettersMalformedVaultPayloadBeforeAdapter(t *testing.T) {
	task := identityDeliveryTestTask()
	store := &identityDeliveryWorkerStore{tasks: taskSlice(task)}
	secret := identityDeliveryTestSecret(task)
	secret.ChallengeID = "ivc_other"
	secret.Code = "secret-code"
	vault := &identityDeliveryWorkerVault{secret: secret}
	smtp := &identityDeliveryWorkerAdapter{}
	sms := &identityDeliveryWorkerAdapter{}

	result, err := newIdentityDeliveryTestWorker(
		t, store, vault, smtp, sms, nil, nil,
	).ProcessBatch(context.Background(), task.TenantID, task.ProjectID, 10)
	if err != nil {
		t.Fatal(err)
	}
	vaultCalls, _ := vault.snapshot()
	smtpCalls, _, _ := smtp.snapshot()
	if result.DeadLettered != 1 || vaultCalls != 1 || smtpCalls != 0 ||
		store.deadSnapshot() != identityDeliveryFailureMalformedPayload {
		t.Fatalf("malformed vault payload reached adapter: result=%#v vault=%d smtp=%d code=%q", result, vaultCalls, smtpCalls, store.deadSnapshot())
	}
}

func TestIdentityDeliveryWorkerRejectsFenceLossAtCompletion(t *testing.T) {
	task := identityDeliveryTestTask()
	store := &identityDeliveryWorkerStore{
		tasks: taskSlice(task), completeErr: ErrIdentityDeliveryLeaseLost,
	}
	vault := &identityDeliveryWorkerVault{secret: identityDeliveryTestSecret(task)}
	smtp := &identityDeliveryWorkerAdapter{}
	sms := &identityDeliveryWorkerAdapter{}

	result, err := newIdentityDeliveryTestWorker(
		t, store, vault, smtp, sms, nil, nil,
	).ProcessBatch(context.Background(), task.TenantID, task.ProjectID, 10)
	if !errors.Is(err, ErrIdentityDeliveryLeaseLost) || result.LeaseRejected != 1 ||
		result.Delivered != 0 {
		t.Fatalf("stale completion fence was accepted: result=%#v err=%v", result, err)
	}
	_, _, completed, retried, dead, _ := store.counts()
	if completed != 1 || retried != 0 || dead != 0 {
		t.Fatalf("completion fence loss caused another transition: complete=%d retry=%d dead=%d", completed, retried, dead)
	}
}

func TestIdentityDeliveryWorkerRedriveRequiresAndPreservesAuditEvidence(t *testing.T) {
	task := identityDeliveryTestTask()
	store := &identityDeliveryWorkerStore{}
	vault := &identityDeliveryWorkerVault{}
	smtp := &identityDeliveryWorkerAdapter{}
	sms := &identityDeliveryWorkerAdapter{}
	telemetry := &identityDeliveryWorkerTelemetry{}
	worker := newIdentityDeliveryTestWorker(t, store, vault, smtp, sms, telemetry, nil)

	invalid := IdentityDeliveryRedriveRequest{
		TaskID: task.ID, TenantID: task.TenantID, ProjectID: task.ProjectID,
		ExpectedLeaseGeneration: task.LeaseGeneration, ActorID: "operator-1",
		ReasonCode: "", RequestID: "request-1",
	}
	if _, err := worker.Redrive(context.Background(), invalid); err == nil {
		t.Fatal("redrive without an audited reason was accepted")
	}
	_, _, _, _, _, redrives := store.counts()
	if redrives != 0 {
		t.Fatal("invalid redrive reached the store")
	}

	request := invalid
	request.ReasonCode = "operator_retry"
	receipt, err := worker.Redrive(context.Background(), request)
	if err != nil {
		t.Fatal(err)
	}
	command := store.redriveSnapshot()
	if receipt.TaskID != task.ID || receipt.LeaseGeneration != task.LeaseGeneration+1 ||
		receipt.AuditID == "" || command.ActorID != request.ActorID ||
		command.ReasonCode != request.ReasonCode || command.RequestID != request.RequestID ||
		!command.RequestedAt.Equal(identityDeliveryTestNow()) {
		t.Fatalf("redrive audit evidence was not preserved: receipt=%#v command=%#v", receipt, command)
	}
	events := telemetry.snapshot()
	if len(events) != 1 || events[0].Type != IdentityDeliveryEventRedriven {
		t.Fatalf("missing public redrive telemetry: %#v", events)
	}
	serialized := fmt.Sprintf("%#v", events)
	if strings.Contains(serialized, request.ActorID) || strings.Contains(serialized, request.RequestID) {
		t.Fatalf("audit identity leaked into telemetry: %s", serialized)
	}
}

func TestIdentityDeliveryWorkerRejectsUnauditedRedriveReceipt(t *testing.T) {
	task := identityDeliveryTestTask()
	store := &identityDeliveryWorkerStore{
		redriveReceipt: IdentityDeliveryRedriveReceipt{
			TaskID: task.ID, LeaseGeneration: task.LeaseGeneration + 1,
			RedrivenAt: identityDeliveryTestNow(),
		},
	}
	worker := newIdentityDeliveryTestWorker(
		t, store, &identityDeliveryWorkerVault{},
		&identityDeliveryWorkerAdapter{}, &identityDeliveryWorkerAdapter{}, nil, nil,
	)
	_, err := worker.Redrive(context.Background(), IdentityDeliveryRedriveRequest{
		TaskID: task.ID, TenantID: task.TenantID, ProjectID: task.ProjectID,
		ExpectedLeaseGeneration: task.LeaseGeneration, ActorID: "operator-1",
		ReasonCode: "operator_retry", RequestID: "request-1",
	})
	if err == nil || !strings.Contains(err.Error(), "receipt is invalid") {
		t.Fatalf("unaudited redrive receipt was accepted: %v", err)
	}
}

func TestIdentityDeliveryDaemonGracefullyCancelsInFlightProvider(t *testing.T) {
	task := identityDeliveryTestTask()
	store := &identityDeliveryWorkerStore{tasks: taskSlice(task)}
	vault := &identityDeliveryWorkerVault{secret: identityDeliveryTestSecret(task)}
	started := make(chan struct{})
	smtp := &identityDeliveryWorkerAdapter{
		started: started,
		sendFn: func(ctx context.Context, _ IdentityVerificationDelivery) error {
			<-ctx.Done()
			return ctx.Err()
		},
	}
	sms := &identityDeliveryWorkerAdapter{}
	worker := newIdentityDeliveryTestWorker(t, store, vault, smtp, sms, nil, nil)
	ctx, cancel := context.WithCancel(context.Background())
	type runResponse struct {
		result IdentityDeliveryRunResult
		err    error
	}
	response := make(chan runResponse, 1)
	go func() {
		result, err := worker.Run(ctx, IdentityDeliveryDaemonOptions{
			TenantID: task.TenantID, ProjectID: task.ProjectID,
			BatchSize: 10, PollInterval: time.Millisecond,
		})
		response <- runResponse{result: result, err: err}
	}()

	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("provider did not start")
	}
	cancel()
	select {
	case run := <-response:
		if run.err != nil || !run.result.GracefulShutdown || run.result.Claimed != 1 {
			t.Fatalf("daemon did not shut down gracefully: result=%#v err=%v", run.result, run.err)
		}
	case <-time.After(time.Second):
		t.Fatal("daemon did not stop after context cancellation")
	}
	_, _, completed, retried, dead, _ := store.counts()
	if completed != 0 || retried != 0 || dead != 0 {
		t.Fatalf("shutdown converted cancellation into a transition: complete=%d retry=%d dead=%d", completed, retried, dead)
	}
}

func TestIdentityDeliveryWorkerTelemetryFailureDoesNotChangeDurableOutcome(t *testing.T) {
	task := identityDeliveryTestTask()
	store := &identityDeliveryWorkerStore{tasks: taskSlice(task)}
	vault := &identityDeliveryWorkerVault{secret: identityDeliveryTestSecret(task)}
	telemetry := &identityDeliveryWorkerTelemetry{err: errors.New("telemetry unavailable")}

	result, err := newIdentityDeliveryTestWorker(
		t, store, vault, &identityDeliveryWorkerAdapter{},
		&identityDeliveryWorkerAdapter{}, telemetry, nil,
	).ProcessBatch(context.Background(), task.TenantID, task.ProjectID, 10)
	if err != nil {
		t.Fatal(err)
	}
	if result.Delivered != 1 || result.TelemetryFailures != 1 {
		t.Fatalf("telemetry failure changed delivery outcome: %#v", result)
	}
}

func TestIdentityDeliveryBackoffCapsWithoutOverflow(t *testing.T) {
	if got := identityDeliveryBackoff(1, time.Second, time.Minute); got != time.Second {
		t.Fatalf("first backoff = %s", got)
	}
	if got := identityDeliveryBackoff(1000, time.Second, time.Minute); got != time.Minute {
		t.Fatalf("capped backoff = %s", got)
	}
}

func taskSlice(task IdentityDeliveryTask) []IdentityDeliveryTask {
	return []IdentityDeliveryTask{task}
}
