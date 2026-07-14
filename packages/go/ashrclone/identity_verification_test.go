package ashrclone

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

type countingIdentityVerificationSender struct {
	calls int
	err   error
}

func (sender *countingIdentityVerificationSender) SendIdentityVerification(
	context.Context,
	IdentityVerificationDelivery,
) error {
	sender.calls++
	return sender.err
}

type countingIdentityVerificationStore struct {
	delegate     IdentityVerificationStore
	createCalls  int
	consumeCalls int
}

func (store *countingIdentityVerificationStore) CreateIdentityVerificationChallenge(
	ctx context.Context,
	challenge IdentityVerificationChallenge,
	cooldown time.Duration,
) error {
	store.createCalls++
	return store.delegate.CreateIdentityVerificationChallenge(ctx, challenge, cooldown)
}

func (store *countingIdentityVerificationStore) ConsumeIdentityVerificationChallenge(
	ctx context.Context,
	challengeID string,
	verify func(IdentityVerificationChallenge) error,
) (IdentityVerificationChallenge, error) {
	store.consumeCalls++
	return store.delegate.ConsumeIdentityVerificationChallenge(ctx, challengeID, verify)
}

type productionOutboxVerificationStore struct {
	createCalls           int
	consumeCalls          int
	createErr             error
	deliveryReservationID string
	opaqueRef             string
}

func (store *productionOutboxVerificationStore) CreateIdentityVerificationChallenge(
	context.Context,
	IdentityVerificationChallenge,
	time.Duration,
) error {
	store.createCalls++
	return store.createErr
}

func (store *productionOutboxVerificationStore) ConsumeIdentityVerificationChallenge(
	context.Context,
	string,
	func(IdentityVerificationChallenge) error,
) (IdentityVerificationChallenge, error) {
	store.consumeCalls++
	return IdentityVerificationChallenge{}, nil
}

func (*productionOutboxVerificationStore) IsProductionIdentityVerificationStore() {}

func (*productionOutboxVerificationStore) UsesTransactionalIdentityVerificationOutbox() {}

func (*productionOutboxVerificationStore) IdentityVerificationDeliveryScope() (string, string) {
	return "tenant-outbox", "project-outbox"
}

func (store *productionOutboxVerificationStore) CreateIdentityVerificationChallengeWithDelivery(
	_ context.Context,
	_ IdentityVerificationChallenge,
	_ time.Duration,
	deliveryReservationID string,
	opaqueRef string,
) error {
	store.createCalls++
	store.deliveryReservationID = deliveryReservationID
	store.opaqueRef = opaqueRef
	return store.createErr
}

type recordingIdentityDeliveryVault struct {
	sealCalls         int
	deleteCalls       int
	sealRequest       IdentityDeliverySealRequest
	deleteRef         string
	sealRef           string
	sealErr           error
	deleteErr         error
	deleteHadDeadline bool
	deleteContextErr  error
}

func (vault *recordingIdentityDeliveryVault) SealIdentityDelivery(
	_ context.Context,
	request IdentityDeliverySealRequest,
) (string, error) {
	vault.sealCalls++
	vault.sealRequest = request
	if vault.sealRef == "" {
		vault.sealRef = "vault:identity-delivery/sealed-1"
	}
	return vault.sealRef, vault.sealErr
}

func (vault *recordingIdentityDeliveryVault) DeleteIdentityDelivery(
	ctx context.Context,
	opaqueRef string,
) error {
	vault.deleteCalls++
	vault.deleteRef = opaqueRef
	_, vault.deleteHadDeadline = ctx.Deadline()
	vault.deleteContextErr = ctx.Err()
	return vault.deleteErr
}

type productionOutboxVerificationCoordinator struct {
	calls int
}

func (coordinator *productionOutboxVerificationCoordinator) CompleteIdentityVerification(
	context.Context,
	IdentityVerificationCompletionCommand,
) (IdentityVerificationResultDTO, error) {
	coordinator.calls++
	return IdentityVerificationResultDTO{}, nil
}

func (*productionOutboxVerificationCoordinator) IsProductionIdentityVerificationTransactionCoordinator() {
}

type verificationClock struct {
	mu  sync.Mutex
	now time.Time
}

func (clock *verificationClock) Now() time.Time {
	clock.mu.Lock()
	defer clock.mu.Unlock()
	return clock.now
}

func (clock *verificationClock) Add(duration time.Duration) {
	clock.mu.Lock()
	clock.now = clock.now.Add(duration)
	clock.mu.Unlock()
}

func newVerificationTestService(t *testing.T) (*IdentityVerificationService, *MemoryIdentityVerificationSender, *UnifiedIdentityService, *verificationClock) {
	t.Helper()
	clock := &verificationClock{now: time.Date(2026, 7, 10, 8, 0, 0, 0, time.UTC)}
	identity, err := NewUnifiedIdentityService(UnifiedIdentityServiceOptions{
		Now: clock.Now, FingerprintKey: []byte("identity-fingerprint-key-32-bytes!!"),
	})
	if err != nil {
		t.Fatal(err)
	}
	sender := &MemoryIdentityVerificationSender{}
	service, err := NewIdentityVerificationService(IdentityVerificationServiceOptions{
		Store: NewMemoryIdentityVerificationStore(clock.Now), Sender: sender, Identity: identity,
		Now: clock.Now, DigestKey: []byte("verification-hmac-key-at-least-32-bytes"),
		TTL: 5 * time.Minute, AttemptCap: 3, ResendCooldown: time.Minute,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(service.Close)
	return service, sender, identity, clock
}

func startVerification(t *testing.T, service *IdentityVerificationService, request IdentityVerificationStartRequest) IdentityVerificationChallengeDTO {
	t.Helper()
	result, err := service.Start(context.Background(), request)
	if err != nil {
		t.Fatalf("start verification: %v", err)
	}
	return result
}

func lastVerificationCode(t *testing.T, sender *MemoryIdentityVerificationSender) string {
	t.Helper()
	deliveries := sender.Deliveries()
	if len(deliveries) == 0 {
		t.Fatal("verification sender received no delivery")
	}
	return deliveries[len(deliveries)-1].Code
}

func TestIdentityVerificationProductionStartUsesOnlyTransactionalOutbox(t *testing.T) {
	now := time.Date(2026, 7, 11, 10, 0, 0, 0, time.UTC)
	store := &productionOutboxVerificationStore{}
	sender := &countingIdentityVerificationSender{
		err: IdentityVerificationError{Code: "provider_must_not_be_called"},
	}
	coordinator := &productionOutboxVerificationCoordinator{}
	vault := &recordingIdentityDeliveryVault{}
	service, err := NewIdentityVerificationService(IdentityVerificationServiceOptions{
		Store:                  store,
		Sender:                 sender,
		DeliveryVaultSealer:    vault,
		DeliveryVaultDeleter:   vault,
		TransactionCoordinator: coordinator,
		Now:                    func() time.Time { return now },
		Random:                 bytes.NewReader(bytes.Repeat([]byte{0x31}, 128)),
		DigestKey:              []byte("production-verification-hmac-key-32-bytes"),
		TTL:                    5 * time.Minute,
		AttemptCap:             3,
		ResendCooldown:         time.Minute,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(service.Close)

	result, err := service.Start(context.Background(), IdentityVerificationStartRequest{
		Channel: IdentityVerificationEmail, Identifier: "outbox@example.test",
		Purpose: IdentityVerificationBinding, TenantID: "tenant-outbox",
	})
	if err != nil || result.ChallengeID == "" {
		t.Fatalf("durable start failed: result=%#v err=%v", result, err)
	}
	if service.DeliveryMode() != IdentityVerificationDeliveryTransactionalOutbox {
		t.Fatalf("delivery mode=%q", service.DeliveryMode())
	}
	if store.createCalls != 1 || sender.calls != 0 || store.consumeCalls != 0 {
		t.Fatalf(
			"durable side effects create=%d provider=%d consume=%d",
			store.createCalls,
			sender.calls,
			store.consumeCalls,
		)
	}
	if vault.sealCalls != 1 || vault.deleteCalls != 0 ||
		store.deliveryReservationID == "" ||
		store.deliveryReservationID != vault.sealRequest.ReservationID ||
		vault.sealRequest.ChallengeHandle != result.ChallengeID ||
		store.opaqueRef != vault.sealRef {
		t.Fatal("durable seal binding was not preserved")
	}

	failedStore := &productionOutboxVerificationStore{
		createErr: IdentityVerificationError{Code: "verification_store_unavailable"},
	}
	failedSender := &countingIdentityVerificationSender{}
	failedVault := &recordingIdentityDeliveryVault{}
	failedService, err := NewIdentityVerificationService(IdentityVerificationServiceOptions{
		Store: failedStore, Sender: failedSender,
		DeliveryVaultSealer: failedVault, DeliveryVaultDeleter: failedVault,
		TransactionCoordinator: &productionOutboxVerificationCoordinator{},
		Now:                    func() time.Time { return now },
		Random:                 bytes.NewReader(bytes.Repeat([]byte{0x32}, 128)),
		DigestKey:              []byte("production-verification-hmac-key-32-bytes"),
		TTL:                    5 * time.Minute,
		AttemptCap:             3,
		ResendCooldown:         time.Minute,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(failedService.Close)
	_, err = failedService.Start(context.Background(), IdentityVerificationStartRequest{
		Channel: IdentityVerificationEmail, Identifier: "outbox-failure@example.test",
		Purpose: IdentityVerificationBinding, TenantID: "tenant-outbox",
	})
	if verificationErrorCode(err) != "verification_store_unavailable" {
		t.Fatalf("durable enqueue failure was remapped incorrectly: %v", err)
	}
	if failedStore.createCalls != 1 || failedSender.calls != 0 || failedStore.consumeCalls != 0 {
		t.Fatalf(
			"failed durable side effects create=%d provider=%d consume=%d",
			failedStore.createCalls,
			failedSender.calls,
			failedStore.consumeCalls,
		)
	}
	if failedVault.sealCalls != 1 || failedVault.deleteCalls != 1 ||
		failedVault.deleteRef != failedVault.sealRef {
		t.Fatal("failed durable enqueue was not compensated")
	}
}

func TestIdentityVerificationProductionDeliveryFailsClosedAndCompensates(t *testing.T) {
	now := time.Date(2026, 7, 11, 10, 15, 0, 0, time.UTC)
	baseOptions := func(
		store *productionOutboxVerificationStore,
		vault *recordingIdentityDeliveryVault,
	) IdentityVerificationServiceOptions {
		return IdentityVerificationServiceOptions{
			Store: store, TransactionCoordinator: &productionOutboxVerificationCoordinator{},
			DeliveryVaultSealer: vault, DeliveryVaultDeleter: vault,
			Now:       func() time.Time { return now },
			Random:    bytes.NewReader(bytes.Repeat([]byte{0x39}, 256)),
			DigestKey: []byte("production-verification-hmac-key-32-bytes"),
			TTL:       5 * time.Minute, AttemptCap: 3, ResendCooldown: time.Minute,
		}
	}

	t.Run("missing vault capabilities", func(t *testing.T) {
		options := baseOptions(&productionOutboxVerificationStore{}, &recordingIdentityDeliveryVault{})
		options.DeliveryVaultSealer = nil
		if _, err := NewIdentityVerificationService(options); err == nil {
			t.Fatal("production service accepted a missing vault sealer")
		}
		options = baseOptions(&productionOutboxVerificationStore{}, &recordingIdentityDeliveryVault{})
		options.DeliveryVaultDeleter = nil
		if _, err := NewIdentityVerificationService(options); err == nil {
			t.Fatal("production service accepted a missing vault deleter")
		}
	})

	t.Run("seal failure does not write database", func(t *testing.T) {
		store := &productionOutboxVerificationStore{}
		vault := &recordingIdentityDeliveryVault{sealErr: errors.New("private vault failure")}
		service, err := NewIdentityVerificationService(baseOptions(store, vault))
		if err != nil {
			t.Fatal(err)
		}
		defer service.Close()
		_, err = service.Start(context.Background(), IdentityVerificationStartRequest{
			Channel: IdentityVerificationEmail, Identifier: "seal-failure@example.test",
			Purpose: IdentityVerificationBinding, TenantID: "tenant-outbox",
		})
		if verificationErrorCode(err) != "verification_delivery_unavailable" ||
			store.createCalls != 0 || vault.deleteCalls != 0 {
			t.Fatalf("seal failure crossed durable boundary: code=%q create=%d delete=%d", verificationErrorCode(err), store.createCalls, vault.deleteCalls)
		}
	})

	t.Run("database failure deletes seal despite canceled request", func(t *testing.T) {
		store := &productionOutboxVerificationStore{
			createErr: IdentityVerificationError{Code: "verification_store_unavailable"},
		}
		vault := &recordingIdentityDeliveryVault{}
		service, err := NewIdentityVerificationService(baseOptions(store, vault))
		if err != nil {
			t.Fatal(err)
		}
		defer service.Close()
		ctx, cancel := context.WithCancel(context.Background())
		cancel()
		_, err = service.Start(ctx, IdentityVerificationStartRequest{
			Channel: IdentityVerificationEmail, Identifier: "rollback@example.test",
			Purpose: IdentityVerificationBinding, TenantID: "tenant-outbox",
		})
		if verificationErrorCode(err) != "verification_store_unavailable" ||
			vault.deleteCalls != 1 || !vault.deleteHadDeadline || vault.deleteContextErr != nil {
			t.Fatalf("seal compensation was not detached and bounded: code=%q calls=%d deadline=%v context=%v", verificationErrorCode(err), vault.deleteCalls, vault.deleteHadDeadline, vault.deleteContextErr)
		}
	})

	t.Run("compensation failure is public safe", func(t *testing.T) {
		const secret = "private-vault-secret-value"
		store := &productionOutboxVerificationStore{createErr: errors.New(secret)}
		vault := &recordingIdentityDeliveryVault{deleteErr: errors.New(secret)}
		service, err := NewIdentityVerificationService(baseOptions(store, vault))
		if err != nil {
			t.Fatal(err)
		}
		defer service.Close()
		_, err = service.Start(context.Background(), IdentityVerificationStartRequest{
			Channel: IdentityVerificationEmail, Identifier: "compensation@example.test",
			Purpose: IdentityVerificationBinding, TenantID: "tenant-outbox",
		})
		if verificationErrorCode(err) != "verification_delivery_compensation_failed" ||
			strings.Contains(err.Error(), secret) {
			t.Fatalf("unsafe compensation failure: %v", err)
		}
	})

	t.Run("unknown commit preserves sealed payload for reconciliation", func(t *testing.T) {
		store := &productionOutboxVerificationStore{
			createErr: ErrIdentityVerificationDeliveryCommitUnknown,
		}
		vault := &recordingIdentityDeliveryVault{}
		service, err := NewIdentityVerificationService(baseOptions(store, vault))
		if err != nil {
			t.Fatal(err)
		}
		defer service.Close()
		_, err = service.Start(context.Background(), IdentityVerificationStartRequest{
			Channel: IdentityVerificationEmail, Identifier: "commit-unknown@example.test",
			Purpose: IdentityVerificationBinding, TenantID: "tenant-outbox",
		})
		if verificationErrorCode(err) != "verification_delivery_commit_unknown" ||
			vault.sealCalls != 1 || vault.deleteCalls != 0 {
			t.Fatalf("unknown commit deleted a potentially committed payload: code=%q seal=%d delete=%d", verificationErrorCode(err), vault.sealCalls, vault.deleteCalls)
		}
	})
}

func TestIdentityVerificationDeliveryModesFailClosedAndCallSynchronousProviderOnce(t *testing.T) {
	now := time.Date(2026, 7, 11, 10, 30, 0, 0, time.UTC)
	identity, err := NewUnifiedIdentityService(UnifiedIdentityServiceOptions{
		Now: func() time.Time { return now }, FingerprintKey: []byte("delivery-mode-fingerprint-key-32-bytes"),
	})
	if err != nil {
		t.Fatal(err)
	}

	t.Run("invalid mode combinations", func(t *testing.T) {
		_, err := NewIdentityVerificationService(IdentityVerificationServiceOptions{
			Store: &productionOutboxVerificationStore{}, Sender: &countingIdentityVerificationSender{},
			DeliveryMode:           IdentityVerificationDeliverySynchronous,
			TransactionCoordinator: &productionOutboxVerificationCoordinator{},
			DigestKey:              []byte("production-verification-hmac-key-32-bytes"),
		})
		if err == nil {
			t.Fatal("production store accepted synchronous delivery")
		}
		_, err = NewIdentityVerificationService(IdentityVerificationServiceOptions{
			Store:        NewMemoryIdentityVerificationStore(func() time.Time { return now }),
			DeliveryMode: IdentityVerificationDeliveryTransactionalOutbox,
			Identity:     identity,
			DigestKey:    []byte("development-verification-key-32-bytes"),
		})
		if err == nil {
			t.Fatal("memory store accepted transactional outbox delivery")
		}
	})

	for _, test := range []struct {
		name         string
		identifier   string
		providerErr  error
		wantErrCode  string
		wantConsumes int
	}{
		{name: "success", identifier: "sync-success@example.test"},
		{name: "provider failure", identifier: "sync-failure@example.test", providerErr: IdentityVerificationError{Code: "provider_down"}, wantErrCode: "delivery_failed", wantConsumes: 1},
	} {
		t.Run(test.name, func(t *testing.T) {
			store := &countingIdentityVerificationStore{
				delegate: NewMemoryIdentityVerificationStore(func() time.Time { return now }),
			}
			sender := &countingIdentityVerificationSender{err: test.providerErr}
			service, err := NewIdentityVerificationService(IdentityVerificationServiceOptions{
				Store: store, Sender: sender, Identity: identity,
				DeliveryMode:   IdentityVerificationDeliverySynchronous,
				Now:            func() time.Time { return now },
				Random:         bytes.NewReader(bytes.Repeat([]byte{0x41}, 128)),
				DigestKey:      []byte("development-verification-key-32-bytes"),
				TTL:            5 * time.Minute,
				AttemptCap:     3,
				ResendCooldown: time.Minute,
			})
			if err != nil {
				t.Fatal(err)
			}
			t.Cleanup(service.Close)
			_, startErr := service.Start(context.Background(), IdentityVerificationStartRequest{
				Channel: IdentityVerificationEmail, Identifier: test.identifier,
				Purpose: IdentityVerificationBinding, TenantID: "tenant-memory",
			})
			if (test.wantErrCode == "" && startErr != nil) ||
				(test.wantErrCode != "" && verificationErrorCode(startErr) != test.wantErrCode) {
				t.Fatalf("start error=%v, want code %q", startErr, test.wantErrCode)
			}
			if store.createCalls != 1 || sender.calls != 1 || store.consumeCalls != test.wantConsumes {
				t.Fatalf(
					"synchronous side effects create=%d provider=%d consume=%d",
					store.createCalls,
					sender.calls,
					store.consumeCalls,
				)
			}
		})
	}
}

func TestIdentityVerificationBindingCreatesCredentialWithoutImplicitMerge(t *testing.T) {
	service, sender, identity, clock := newVerificationTestService(t)
	first := startVerification(t, service, IdentityVerificationStartRequest{
		Channel: IdentityVerificationEmail, Identifier: "User@Example.com",
		Purpose: IdentityVerificationBinding, TenantID: "tenant-a",
	})
	code := lastVerificationCode(t, sender)
	result, err := service.Complete(context.Background(), IdentityVerificationCompleteRequest{
		ChallengeID: first.ChallengeID, Code: code, Channel: IdentityVerificationEmail,
		Identifier: "user@example.com", Purpose: IdentityVerificationBinding, TenantID: "tenant-a",
	})
	if err != nil {
		t.Fatalf("complete first binding: %v", err)
	}
	if !result.Created || result.Account.CredentialCount != 1 || result.Credential.Kind != IdentityCredentialEmail {
		t.Fatalf("unexpected binding result: %#v", result)
	}

	secondAccount, err := identity.CreateAccount(CreateIdentityAccountRequest{})
	if err != nil {
		t.Fatal(err)
	}
	clock.Add(time.Minute)
	second := startVerification(t, service, IdentityVerificationStartRequest{
		Channel: IdentityVerificationEmail, Identifier: "USER@example.com",
		Purpose: IdentityVerificationBinding, TenantID: "tenant-a", AccountID: secondAccount.AccountID,
	})
	_, err = service.Complete(context.Background(), IdentityVerificationCompleteRequest{
		ChallengeID: second.ChallengeID, Code: lastVerificationCode(t, sender),
		Channel: IdentityVerificationEmail, Identifier: "user@example.com",
		Purpose: IdentityVerificationBinding, TenantID: "tenant-a", AccountID: secondAccount.AccountID,
	})
	if identityErrorCode(err) != "credential_link_conflict" {
		t.Fatalf("same email should conflict rather than merge accounts, got %v", err)
	}
	unchanged, _ := identity.GetAccount(secondAccount.AccountID)
	if unchanged.CredentialCount != 0 {
		t.Fatalf("conflicting binding mutated target account: %#v", unchanged)
	}
}

func TestIdentityVerificationTTLAttemptsCooldownAndSingleUse(t *testing.T) {
	service, sender, _, clock := newVerificationTestService(t)
	request := IdentityVerificationStartRequest{
		Channel: IdentityVerificationPhone, Identifier: "+86 138-0013-8000",
		Purpose: IdentityVerificationBinding, TenantID: "tenant-a",
	}
	challenge := startVerification(t, service, request)
	if _, err := service.Start(context.Background(), request); verificationErrorCode(err) != "verification_resend_cooldown" {
		t.Fatalf("expected resend cooldown, got %v", err)
	}
	code := lastVerificationCode(t, sender)
	for attempt := 0; attempt < 2; attempt++ {
		_, err := service.Complete(context.Background(), IdentityVerificationCompleteRequest{
			ChallengeID: challenge.ChallengeID, Code: "000000", Channel: request.Channel,
			Identifier: request.Identifier, Purpose: request.Purpose, TenantID: request.TenantID,
		})
		if verificationErrorCode(err) != "verification_code_invalid" {
			t.Fatalf("attempt %d: expected invalid code, got %v", attempt, err)
		}
	}
	result, err := service.Complete(context.Background(), IdentityVerificationCompleteRequest{
		ChallengeID: challenge.ChallengeID, Code: code, Channel: request.Channel,
		Identifier: request.Identifier, Purpose: request.Purpose, TenantID: request.TenantID,
	})
	if err != nil || result.Account.AccountID == "" {
		t.Fatalf("valid final attempt failed: result=%#v err=%v", result, err)
	}
	if _, err := service.Complete(context.Background(), IdentityVerificationCompleteRequest{
		ChallengeID: challenge.ChallengeID, Code: code, Channel: request.Channel,
		Identifier: request.Identifier, Purpose: request.Purpose, TenantID: request.TenantID,
	}); !errorsIsVerificationConsumed(err) {
		t.Fatalf("challenge was reusable: %v", err)
	}

	clock.Add(time.Minute)
	expiring := startVerification(t, service, request)
	clock.Add(6 * time.Minute)
	_, err = service.Complete(context.Background(), IdentityVerificationCompleteRequest{
		ChallengeID: expiring.ChallengeID, Code: lastVerificationCode(t, sender), Channel: request.Channel,
		Identifier: request.Identifier, Purpose: request.Purpose, TenantID: request.TenantID,
	})
	if verificationErrorCode(err) != "verification_expired" {
		t.Fatalf("expired challenge accepted: %v", err)
	}
}

func errorsIsVerificationConsumed(err error) bool {
	return err == ErrIdentityVerificationConsumed
}

func TestIdentityVerificationConcurrentCompleteIsSingleUse(t *testing.T) {
	service, sender, _, _ := newVerificationTestService(t)
	request := IdentityVerificationStartRequest{
		Channel: IdentityVerificationEmail, Identifier: "race@example.com",
		Purpose: IdentityVerificationBinding, TenantID: "tenant-a",
	}
	challenge := startVerification(t, service, request)
	code := lastVerificationCode(t, sender)
	start := make(chan struct{})
	errors := make(chan error, 8)
	var wait sync.WaitGroup
	for index := 0; index < cap(errors); index++ {
		wait.Add(1)
		go func() {
			defer wait.Done()
			<-start
			_, err := service.Complete(context.Background(), IdentityVerificationCompleteRequest{
				ChallengeID: challenge.ChallengeID, Code: code, Channel: request.Channel,
				Identifier: request.Identifier, Purpose: request.Purpose, TenantID: request.TenantID,
			})
			errors <- err
		}()
	}
	close(start)
	wait.Wait()
	close(errors)
	successes := 0
	consumed := 0
	for err := range errors {
		switch {
		case err == nil:
			successes++
		case err == ErrIdentityVerificationConsumed:
			consumed++
		default:
			t.Fatalf("unexpected concurrent completion result: %v", err)
		}
	}
	if successes != 1 || consumed != 7 {
		t.Fatalf("challenge was not atomically single-use: successes=%d consumed=%d", successes, consumed)
	}
}

func TestIdentityVerificationDeliveryFailureInvalidatesChallenge(t *testing.T) {
	service, sender, _, clock := newVerificationTestService(t)
	sender.SetError(IdentityVerificationError{Code: "provider_unavailable"})
	_, err := service.Start(context.Background(), IdentityVerificationStartRequest{
		Channel: IdentityVerificationEmail, Identifier: "delivery@example.com",
		Purpose: IdentityVerificationBinding, TenantID: "tenant-a",
	})
	if verificationErrorCode(err) != "delivery_failed" {
		t.Fatalf("sender failure was not normalized: %v", err)
	}
	events := service.AuditEvents()
	if len(events) == 0 || events[len(events)-1].Outcome != "failed" || events[len(events)-1].Reason != "delivery_failed" {
		t.Fatalf("delivery failure audit is incomplete: %#v", events)
	}
	clock.Add(time.Minute)
	sender.SetError(nil)
	if _, err := service.Start(context.Background(), IdentityVerificationStartRequest{
		Channel: IdentityVerificationEmail, Identifier: "delivery@example.com",
		Purpose: IdentityVerificationBinding, TenantID: "tenant-a",
	}); err != nil {
		t.Fatalf("failed delivery permanently blocked resend: %v", err)
	}
}

func TestIdentityVerificationLoginRequiresBoundAccountAndScope(t *testing.T) {
	service, sender, identity, _ := newVerificationTestService(t)
	account, err := identity.CreateAccount(CreateIdentityAccountRequest{
		InitialCredential: &IdentityCredentialInput{
			Kind: IdentityCredentialPhone, Provider: IdentityProviderLocal,
			Identifier: "+8613800138000", Verified: true,
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	challenge := startVerification(t, service, IdentityVerificationStartRequest{
		Channel: IdentityVerificationPhone, Identifier: "+8613800138000",
		Purpose: IdentityVerificationLogin, TenantID: "tenant-a", AccountID: account.AccountID,
	})
	code := lastVerificationCode(t, sender)
	_, err = service.Complete(context.Background(), IdentityVerificationCompleteRequest{
		ChallengeID: challenge.ChallengeID, Code: code, Channel: IdentityVerificationPhone,
		Identifier: "+8613800138000", Purpose: IdentityVerificationLogin,
		TenantID: "tenant-b", AccountID: account.AccountID,
	})
	if verificationErrorCode(err) != "verification_scope_mismatch" {
		t.Fatalf("cross-tenant replay was accepted: %v", err)
	}
	result, err := service.Complete(context.Background(), IdentityVerificationCompleteRequest{
		ChallengeID: challenge.ChallengeID, Code: code, Channel: IdentityVerificationPhone,
		Identifier: "+8613800138000", Purpose: IdentityVerificationLogin,
		TenantID: "tenant-a", AccountID: account.AccountID,
	})
	if err != nil || result.Account.AccountID != account.AccountID || result.Created {
		t.Fatalf("bound login failed: result=%#v err=%v", result, err)
	}
}

func TestIdentityVerificationHTTPRejectsLegacyAccountCreationWithoutLeaks(t *testing.T) {
	service, sender, identity, clock := newVerificationTestService(t)
	budget, err := NewMemoryIdentityVerificationAbuseBudget(
		MemoryIdentityVerificationAbuseBudgetOptions{
			Now:       clock.Now,
			DigestKey: []byte("verification-abuse-budget-key-32-bytes"),
			Limits: map[IdentityVerificationAbuseDimension]IdentityVerificationAbuseLimit{
				IdentityVerificationAbuseIdentifier: {Limit: 10, Window: time.Minute},
			},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(budget.Close)
	responsePolicy, err := NewIdentityVerificationResponsePolicy(
		IdentityVerificationResponsePolicyOptions{
			Budget: budget,
			Now:    clock.Now,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	handler := NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		UnifiedIdentity:                    identity,
		IdentityVerification:               service,
		IdentityVerificationResponsePolicy: responsePolicy,
	})
	startBody := `{"channel":"email","identifier":"private@example.com","purpose":"binding","tenant_id":"tenant-a"}`
	startRequest := httptest.NewRequest(http.MethodPost, "/v1/identity-verification/challenges", strings.NewReader(startBody))
	startResponse := httptest.NewRecorder()
	handler.ServeHTTP(startResponse, startRequest)
	if startResponse.Code != http.StatusBadRequest ||
		!strings.Contains(startResponse.Body.String(), `"code":"identity_registration_route_required"`) {
		t.Fatalf("start status=%d body=%s", startResponse.Code, startResponse.Body.String())
	}
	deliveries := sender.Deliveries()
	if len(deliveries) != 0 {
		t.Fatalf("verification sender received %d deliveries", len(deliveries))
	}
	if strings.Contains(strings.ToLower(startResponse.Body.String()), "private@example.com") {
		t.Fatalf("rejection leaked the submitted identifier: %s", startResponse.Body.String())
	}
	encoded, _ := json.Marshal(service.AuditEvents())
	if strings.Contains(strings.ToLower(string(encoded)), "private@example.com") {
		t.Fatalf("audit event leaked verification material: %s", encoded)
	}
}

func verificationBodyContainsSecret(body, code, identifier string) bool {
	return strings.Contains(body, code) || strings.Contains(strings.ToLower(body), strings.ToLower(identifier))
}
