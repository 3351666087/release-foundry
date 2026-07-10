package ashrclone

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

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

func TestIdentityVerificationHTTPNeverReturnsCodeOrIdentifier(t *testing.T) {
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
	if startResponse.Code != http.StatusAccepted {
		t.Fatalf("start status=%d body=%s", startResponse.Code, startResponse.Body.String())
	}
	deliveries := sender.Deliveries()
	if len(deliveries) != 1 {
		t.Fatalf("verification sender received %d deliveries", len(deliveries))
	}
	delivery := deliveries[0]
	code := delivery.Code
	if verificationBodyContainsSecret(startResponse.Body.String(), code, "private@example.com") {
		t.Fatalf("start response leaked verification material: %s", startResponse.Body.String())
	}
	var start IdentityVerificationPublicResponse
	if err := json.Unmarshal(startResponse.Body.Bytes(), &start); err != nil {
		t.Fatal(err)
	}
	if start.Status != "accepted" || strings.Contains(startResponse.Body.String(), delivery.ChallengeID) {
		t.Fatalf("start response was distinguishable or leaked challenge id: %s", startResponse.Body.String())
	}
	verifyBody := `{"challenge_id":"` + delivery.ChallengeID + `","code":"` + code +
		`","channel":"email","identifier":"private@example.com","purpose":"binding","tenant_id":"tenant-a"}`
	verifyRequest := httptest.NewRequest(http.MethodPost, "/v1/identity-verification/verify", strings.NewReader(verifyBody))
	verifyResponse := httptest.NewRecorder()
	handler.ServeHTTP(verifyResponse, verifyRequest)
	if verifyResponse.Code != http.StatusOK {
		t.Fatalf("verify status=%d body=%s", verifyResponse.Code, verifyResponse.Body.String())
	}
	if verificationBodyContainsSecret(verifyResponse.Body.String(), code, "private@example.com") {
		t.Fatalf("verify response leaked verification material: %s", verifyResponse.Body.String())
	}
	encoded, _ := json.Marshal(service.AuditEvents())
	if verificationBodyContainsSecret(string(encoded), code, "private@example.com") {
		t.Fatalf("audit event leaked verification material: %s", encoded)
	}
}

func verificationBodyContainsSecret(body, code, identifier string) bool {
	return strings.Contains(body, code) || strings.Contains(strings.ToLower(body), strings.ToLower(identifier))
}
