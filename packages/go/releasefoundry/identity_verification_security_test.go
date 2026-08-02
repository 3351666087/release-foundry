package releasefoundry

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func newVerificationSecurityBudget(
	t *testing.T,
	clock *verificationClock,
	limits map[IdentityVerificationAbuseDimension]IdentityVerificationAbuseLimit,
) *MemoryIdentityVerificationAbuseBudget {
	t.Helper()
	budget, err := NewMemoryIdentityVerificationAbuseBudget(MemoryIdentityVerificationAbuseBudgetOptions{
		Now: clock.Now, DigestKey: []byte("verification-abuse-budget-key-32-bytes"),
		Limits: limits,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(budget.Close)
	return budget
}

func fullVerificationAbuseSubject() IdentityVerificationAbuseSubject {
	return IdentityVerificationAbuseSubject{
		Operation: "verification.start", IdentifierDigest: "digest-identifier",
		AccountID: "account-sensitive", IPAddress: "203.0.113.42",
		TenantID: "tenant-sensitive", DeviceID: "device-sensitive",
	}
}

func TestMemoryIdentityVerificationAbuseBudgetEnforcesEveryDimension(t *testing.T) {
	dimensions := []IdentityVerificationAbuseDimension{
		IdentityVerificationAbuseIdentifier,
		IdentityVerificationAbuseAccount,
		IdentityVerificationAbuseIP,
		IdentityVerificationAbuseTenant,
		IdentityVerificationAbuseDevice,
	}
	for _, dimension := range dimensions {
		t.Run(string(dimension), func(t *testing.T) {
			clock := &verificationClock{now: time.Date(2026, 7, 11, 1, 0, 0, 0, time.UTC)}
			budget := newVerificationSecurityBudget(t, clock, map[IdentityVerificationAbuseDimension]IdentityVerificationAbuseLimit{
				dimension: {Limit: 1, Window: time.Minute},
			})
			first, err := budget.CheckAndConsume(context.Background(), fullVerificationAbuseSubject())
			if err != nil || !first.Allowed {
				t.Fatalf("first request should be allowed: decision=%#v err=%v", first, err)
			}
			second, err := budget.CheckAndConsume(context.Background(), fullVerificationAbuseSubject())
			if err != nil || second.Allowed || second.RetryAfter != time.Minute {
				t.Fatalf("second request should exhaust %s: decision=%#v err=%v", dimension, second, err)
			}
			if len(second.ExhaustedDimensions) != 1 || second.ExhaustedDimensions[0] != dimension {
				t.Fatalf("unexpected exhausted dimensions: %#v", second.ExhaustedDimensions)
			}
		})
	}
}

func TestMemoryIdentityVerificationAbuseBudgetRejectsAtomically(t *testing.T) {
	clock := &verificationClock{now: time.Date(2026, 7, 11, 2, 0, 0, 0, time.UTC)}
	budget := newVerificationSecurityBudget(t, clock, map[IdentityVerificationAbuseDimension]IdentityVerificationAbuseLimit{
		IdentityVerificationAbuseIdentifier: {Limit: 1, Window: time.Minute},
		IdentityVerificationAbuseTenant:     {Limit: 2, Window: time.Minute},
	})
	subject := fullVerificationAbuseSubject()
	if decision, err := budget.CheckAndConsume(context.Background(), subject); err != nil || !decision.Allowed {
		t.Fatalf("initial consume failed: %#v %v", decision, err)
	}
	changedIdentifier := subject
	changedIdentifier.IdentifierDigest = "another-digest"
	if decision, err := budget.CheckAndConsume(context.Background(), changedIdentifier); err != nil || !decision.Allowed {
		t.Fatalf("second tenant consume failed: %#v %v", decision, err)
	}
	if decision, err := budget.CheckAndConsume(context.Background(), subject); err != nil || decision.Allowed {
		t.Fatalf("identifier exhaustion should reject: %#v %v", decision, err)
	}
	clock.Add(time.Minute)
	if decision, err := budget.CheckAndConsume(context.Background(), subject); err != nil || !decision.Allowed {
		t.Fatalf("rejected request consumed tenant budget or window did not reset: %#v %v", decision, err)
	}
}

func TestMemoryIdentityVerificationAbuseBudgetIsConcurrentAndOperationScoped(t *testing.T) {
	clock := &verificationClock{now: time.Date(2026, 7, 11, 3, 0, 0, 0, time.UTC)}
	budget := newVerificationSecurityBudget(t, clock, map[IdentityVerificationAbuseDimension]IdentityVerificationAbuseLimit{
		IdentityVerificationAbuseIP: {Limit: 8, Window: time.Minute},
	})
	subject := fullVerificationAbuseSubject()
	var allowed atomic.Int64
	var wait sync.WaitGroup
	for index := 0; index < 64; index++ {
		wait.Add(1)
		go func() {
			defer wait.Done()
			decision, err := budget.CheckAndConsume(context.Background(), subject)
			if err != nil {
				t.Errorf("consume: %v", err)
				return
			}
			if decision.Allowed {
				allowed.Add(1)
			}
		}()
	}
	wait.Wait()
	if allowed.Load() != 8 {
		t.Fatalf("concurrent budget allowed %d requests, want 8", allowed.Load())
	}
	subject.Operation = "verification.complete"
	decision, err := budget.CheckAndConsume(context.Background(), subject)
	if err != nil || !decision.Allowed {
		t.Fatalf("separate operation should have a separate budget: %#v %v", decision, err)
	}
}

func TestIdentityVerificationResponsePolicyUnifiesInternalOutcomes(t *testing.T) {
	clock := &verificationClock{now: time.Date(2026, 7, 11, 4, 0, 0, 0, time.UTC)}
	budget := newVerificationSecurityBudget(t, clock, map[IdentityVerificationAbuseDimension]IdentityVerificationAbuseLimit{
		IdentityVerificationAbuseIdentifier: {Limit: 3, Window: time.Minute},
	})
	var slept []time.Duration
	policy, err := NewIdentityVerificationResponsePolicy(IdentityVerificationResponsePolicyOptions{
		Budget: budget, Now: clock.Now, MinimumResponseDelay: 250 * time.Millisecond,
		Sleep: func(_ context.Context, duration time.Duration) error {
			slept = append(slept, duration)
			return nil
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	subject := fullVerificationAbuseSubject()
	internalOutcomes := []error{
		nil,
		IdentityVerificationError{Code: "verification_target_unavailable", Message: "target does not exist"},
		fmt.Errorf("provider rejected destination-sensitive"),
	}
	var baseline IdentityVerificationPublicResponse
	for index, internalErr := range internalOutcomes {
		response, executeErr := policy.Execute(context.Background(), clock.Now(), subject, func(context.Context) error {
			return internalErr
		})
		if executeErr != nil {
			t.Fatalf("outcome %d: %v", index, executeErr)
		}
		if index == 0 {
			baseline = response
		} else if response != baseline {
			t.Fatalf("internal outcome changed public response: got %#v want %#v", response, baseline)
		}
	}
	called := false
	response, executeErr := policy.Execute(context.Background(), clock.Now(), subject, func(context.Context) error {
		called = true
		return nil
	})
	if executeErr != nil || response != baseline {
		t.Fatalf("budget rejection changed response: %#v %v", response, executeErr)
	}
	if called {
		t.Fatal("budget-exhausted operation was executed")
	}
	if len(slept) != 4 {
		t.Fatalf("minimum delay was not applied to every outcome: %#v", slept)
	}
	for _, duration := range slept {
		if duration != 250*time.Millisecond {
			t.Fatalf("unexpected minimum delay: %v", duration)
		}
	}
}

func TestIdentityVerificationResponsePolicyDoesNotLeakSensitiveValues(t *testing.T) {
	clock := &verificationClock{now: time.Date(2026, 7, 11, 5, 0, 0, 0, time.UTC)}
	budget := newVerificationSecurityBudget(t, clock, map[IdentityVerificationAbuseDimension]IdentityVerificationAbuseLimit{
		IdentityVerificationAbuseIdentifier: {Limit: 1, Window: time.Minute},
	})
	policy, err := NewIdentityVerificationResponsePolicy(IdentityVerificationResponsePolicyOptions{
		Budget: budget, Now: clock.Now,
	})
	if err != nil {
		t.Fatal(err)
	}
	subject := fullVerificationAbuseSubject()
	destination := strings.Join([]string{"private", "@", "example.test"}, "")
	response, err := policy.Execute(context.Background(), clock.Now(), subject, func(context.Context) error {
		return fmt.Errorf("no account for %s", destination)
	})
	if err != nil {
		t.Fatal(err)
	}
	public := fmt.Sprintf("%+v", response)
	for _, forbidden := range []string{
		destination, subject.IdentifierDigest, subject.AccountID,
		subject.IPAddress, subject.TenantID, subject.DeviceID, "exist",
	} {
		if strings.Contains(strings.ToLower(public), strings.ToLower(forbidden)) {
			t.Fatalf("public response leaked sensitive or existence data")
		}
	}
}

func TestIdentityVerificationResponsePolicyHonorsCancellation(t *testing.T) {
	clock := &verificationClock{now: time.Date(2026, 7, 11, 6, 0, 0, 0, time.UTC)}
	budget := newVerificationSecurityBudget(t, clock, map[IdentityVerificationAbuseDimension]IdentityVerificationAbuseLimit{
		IdentityVerificationAbuseDevice: {Limit: 1, Window: time.Minute},
	})
	policy, err := NewIdentityVerificationResponsePolicy(IdentityVerificationResponsePolicyOptions{
		Budget: budget, Now: clock.Now, MinimumResponseDelay: time.Second,
		Sleep: func(ctx context.Context, _ time.Duration) error {
			return ctx.Err()
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err = policy.Execute(ctx, clock.Now(), fullVerificationAbuseSubject(), func(context.Context) error {
		t.Fatal("cancelled operation must not execute")
		return nil
	})
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("expected context cancellation, got %v", err)
	}
}

func TestMemoryIdentityVerificationAbuseBudgetRejectsUnsafeConfiguration(t *testing.T) {
	_, err := NewMemoryIdentityVerificationAbuseBudget(MemoryIdentityVerificationAbuseBudgetOptions{
		DigestKey: []byte("short"),
		Limits: map[IdentityVerificationAbuseDimension]IdentityVerificationAbuseLimit{
			IdentityVerificationAbuseIP: {Limit: 1, Window: time.Minute},
		},
	})
	if err == nil {
		t.Fatal("short digest key was accepted")
	}
	_, err = NewMemoryIdentityVerificationAbuseBudget(MemoryIdentityVerificationAbuseBudgetOptions{
		DigestKey: []byte("verification-abuse-budget-key-32-bytes"),
		Limits: map[IdentityVerificationAbuseDimension]IdentityVerificationAbuseLimit{
			"unknown": {Limit: 1, Window: time.Minute},
		},
	})
	if err == nil {
		t.Fatal("unknown dimension was accepted")
	}
}

func TestMemoryIdentityVerificationAbuseBudgetFailsClosedForMissingConfiguredDimension(t *testing.T) {
	clock := &verificationClock{now: time.Date(2026, 7, 11, 7, 0, 0, 0, time.UTC)}
	budget := newVerificationSecurityBudget(t, clock, map[IdentityVerificationAbuseDimension]IdentityVerificationAbuseLimit{
		IdentityVerificationAbuseIdentifier: {Limit: 2, Window: time.Minute},
		IdentityVerificationAbuseIP:         {Limit: 2, Window: time.Minute},
		IdentityVerificationAbuseDevice:     {Limit: 2, Window: time.Minute},
	})
	subject := fullVerificationAbuseSubject()
	subject.IPAddress = ""
	if _, err := budget.CheckAndConsume(context.Background(), subject); err == nil {
		t.Fatal("missing configured IP dimension was accepted")
	}
	subject.IPAddress = "203.0.113.42"
	subject.DeviceID = " "
	if _, err := budget.CheckAndConsume(context.Background(), subject); err == nil {
		t.Fatal("missing configured device dimension was accepted")
	}

	subject.DeviceID = "device-sensitive"
	for attempt := 0; attempt < 2; attempt++ {
		decision, err := budget.CheckAndConsume(context.Background(), subject)
		if err != nil || !decision.Allowed {
			t.Fatalf("invalid subjects consumed a partial budget: decision=%#v err=%v", decision, err)
		}
	}
}
