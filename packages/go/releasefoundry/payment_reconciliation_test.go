package releasefoundry

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"strings"
	"testing"
	"time"
)

const (
	testPaymentPayloadHash = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	testPaymentHeadersHash = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	testPaymentFailureHash = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
)

func newPaymentReconciliationTestService(t *testing.T) (*PaymentReconciliationService, *MemoryPaymentReconciliationRepository) {
	t.Helper()
	repository := NewMemoryPaymentReconciliationRepository()
	now := time.Unix(1_700_000_000, 0).UTC()
	repository.now = func() time.Time {
		now = now.Add(time.Second)
		return now
	}
	service, err := NewPaymentReconciliationService(repository)
	if err != nil {
		t.Fatal(err)
	}
	return service, repository
}

func TestPaymentReconciliationReceivedVerifiedAppliedLifecycle(t *testing.T) {
	service, _ := newPaymentReconciliationTestService(t)
	ctx := context.Background()
	envelope := PaymentEventHashEnvelope{
		Provider: " Stripe ", ProviderEventID: "evt_123", EventType: "checkout.session.completed",
		PayloadSHA256: strings.ToUpper(testPaymentPayloadHash), HeadersSHA256: strings.ToUpper(testPaymentHeadersHash),
	}
	received, err := service.Receive(ctx, "tenant_a", "project_a", envelope)
	if err != nil {
		t.Fatal(err)
	}
	if received.Result.Status != PaymentEventStatusReceived || received.Result.Provider != "stripe" || received.IdempotentReplay {
		t.Fatalf("unexpected received event: %#v", received)
	}
	replayed, err := service.Receive(ctx, "tenant_a", "project_a", envelope)
	if err != nil || !replayed.IdempotentReplay {
		t.Fatalf("receive replay: result=%#v err=%v", replayed, err)
	}
	verified, err := service.Verify(ctx, "tenant_a", "project_a", "STRIPE", "evt_123")
	if err != nil {
		t.Fatal(err)
	}
	if verified.Result.Status != PaymentEventStatusVerified || verified.Result.VerifiedAt == nil {
		t.Fatalf("unexpected verified event: %#v", verified.Result)
	}
	applied, err := service.Apply(ctx, "tenant_a", "project_a", "stripe", "evt_123")
	if err != nil {
		t.Fatal(err)
	}
	if applied.Result.Status != PaymentEventStatusApplied || applied.Result.AppliedAt == nil || applied.Result.FailedAt != nil {
		t.Fatalf("unexpected applied event: %#v", applied.Result)
	}
	appliedReplay, err := service.Apply(ctx, "tenant_a", "project_a", "stripe", "evt_123")
	if err != nil || !appliedReplay.IdempotentReplay {
		t.Fatalf("apply replay: result=%#v err=%v", appliedReplay, err)
	}
}

func TestPaymentReconciliationRejectsEventIDPayloadHashConflict(t *testing.T) {
	service, _ := newPaymentReconciliationTestService(t)
	ctx := context.Background()
	envelope := PaymentEventHashEnvelope{Provider: "stripe", ProviderEventID: "evt_conflict", PayloadSHA256: testPaymentPayloadHash}
	if _, err := service.Receive(ctx, "tenant_a", "project_a", envelope); err != nil {
		t.Fatal(err)
	}
	envelope.PayloadSHA256 = testPaymentHeadersHash
	_, err := service.Receive(ctx, "tenant_a", "project_a", envelope)
	var conflict PaymentReconciliationConflictError
	if !errors.As(err, &conflict) {
		t.Fatalf("expected payment hash conflict, got %v", err)
	}
}

func TestPaymentReconciliationIsolatesTenantAndProjectScopes(t *testing.T) {
	service, _ := newPaymentReconciliationTestService(t)
	ctx := context.Background()
	envelope := PaymentEventHashEnvelope{Provider: "stripe", ProviderEventID: "evt_shared", PayloadSHA256: testPaymentPayloadHash}
	scopes := [][2]string{{"tenant_a", "project_a"}, {"tenant_a", "project_b"}, {"tenant_b", "project_a"}}
	for _, scope := range scopes {
		if _, err := service.Receive(ctx, scope[0], scope[1], envelope); err != nil {
			t.Fatalf("receive %v: %v", scope, err)
		}
	}
	if _, err := service.Verify(ctx, "tenant_a", "project_a", "stripe", "evt_shared"); err != nil {
		t.Fatal(err)
	}
	for _, scope := range scopes[1:] {
		event, err := service.Get(ctx, scope[0], scope[1], "stripe", "evt_shared")
		if err != nil {
			t.Fatal(err)
		}
		if event.Result.Status != PaymentEventStatusReceived {
			t.Fatalf("scope %v leaked transition: %#v", scope, event.Result)
		}
	}
	listed, err := service.List(ctx, "tenant_a", "project_a", "", 100)
	if err != nil {
		t.Fatal(err)
	}
	if listed.Result.Count != 1 || listed.Result.Events[0].ProjectID != "project_a" {
		t.Fatalf("scope leak in list: %#v", listed.Result)
	}
}

func TestPaymentReconciliationEnforcesStateMachineAndFailureIdempotency(t *testing.T) {
	service, _ := newPaymentReconciliationTestService(t)
	ctx := context.Background()
	envelope := PaymentEventHashEnvelope{Provider: "alipay", ProviderEventID: "evt_failed", PayloadSHA256: testPaymentPayloadHash}
	if _, err := service.Receive(ctx, "tenant_a", "project_a", envelope); err != nil {
		t.Fatal(err)
	}
	_, err := service.Apply(ctx, "tenant_a", "project_a", "alipay", "evt_failed")
	var transition PaymentReconciliationTransitionError
	if !errors.As(err, &transition) {
		t.Fatalf("expected invalid transition, got %v", err)
	}
	if _, err := service.Verify(ctx, "tenant_a", "project_a", "alipay", "evt_failed"); err != nil {
		t.Fatal(err)
	}
	failed, err := service.Fail(ctx, "tenant_a", "project_a", "alipay", "evt_failed", testPaymentFailureHash)
	if err != nil || failed.Result.Status != PaymentEventStatusFailed || failed.Result.FailedAt == nil {
		t.Fatalf("fail: result=%#v err=%v", failed, err)
	}
	replay, err := service.Fail(ctx, "tenant_a", "project_a", "alipay", "evt_failed", testPaymentFailureHash)
	if err != nil || !replay.IdempotentReplay {
		t.Fatalf("failure replay: result=%#v err=%v", replay, err)
	}
	_, err = service.Fail(ctx, "tenant_a", "project_a", "alipay", "evt_failed", testPaymentHeadersHash)
	var conflict PaymentReconciliationConflictError
	if !errors.As(err, &conflict) {
		t.Fatalf("expected failure evidence conflict, got %v", err)
	}
	if _, err := service.Apply(ctx, "tenant_a", "project_a", "alipay", "evt_failed"); !errors.As(err, &transition) {
		t.Fatalf("terminal failed event applied: %v", err)
	}
}

func TestPaymentReconciliationPublicJSONContainsNoRawOrSecretMaterial(t *testing.T) {
	service, _ := newPaymentReconciliationTestService(t)
	result, err := service.Receive(context.Background(), "tenant_public", "project_public", PaymentEventHashEnvelope{
		Provider: "wechat_pay", ProviderEventID: "evt_public", EventType: "TRANSACTION.SUCCESS",
		PayloadSHA256: testPaymentPayloadHash, HeadersSHA256: testPaymentHeadersHash,
	})
	if err != nil {
		t.Fatal(err)
	}
	payload, err := json.Marshal(result)
	if err != nil {
		t.Fatal(err)
	}
	serialized := strings.ToLower(string(payload))
	for _, forbidden := range []string{"raw_payload\"", "raw_header\"", "secret\"", "authorization", "signature_value", "webhook_secret"} {
		if strings.Contains(serialized, forbidden) {
			t.Fatalf("public output contains forbidden field %q: %s", forbidden, serialized)
		}
	}
	for key, value := range map[string]bool{
		`"raw_payload_included":false`: result.Result.RawPayloadIncluded,
		`"raw_headers_included":false`: result.Result.RawHeadersIncluded,
		`"secret_value_present":false`: result.Result.SecretValuePresent,
	} {
		if value || !strings.Contains(serialized, key) {
			t.Fatalf("missing public-safety assertion %q: %s", key, serialized)
		}
	}
}

func TestPaymentReconciliationValidatesHashEnvelope(t *testing.T) {
	service, _ := newPaymentReconciliationTestService(t)
	for name, envelope := range map[string]PaymentEventHashEnvelope{
		"provider":     {ProviderEventID: "evt", PayloadSHA256: testPaymentPayloadHash},
		"event id":     {Provider: "stripe", PayloadSHA256: testPaymentPayloadHash},
		"payload hash": {Provider: "stripe", ProviderEventID: "evt", PayloadSHA256: "not-a-hash"},
		"headers hash": {Provider: "stripe", ProviderEventID: "evt", PayloadSHA256: testPaymentPayloadHash, HeadersSHA256: "not-a-hash"},
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := service.Receive(context.Background(), "tenant", "project", envelope); err == nil {
				t.Fatal("expected validation error")
			}
		})
	}
}

func TestPaymentReconciliationSchemaAndRepositoryContracts(t *testing.T) {
	var _ PaymentReconciliationRepository = NewMemoryPaymentReconciliationRepository()
	var _ PaymentReconciliationRepository = (*PostgresRepository)(nil)
	for _, required := range []string{
		"CREATE TABLE IF NOT EXISTS releasefoundry_payment_reconciliation_events",
		"PRIMARY KEY (tenant_id, project_id, provider, provider_event_id)",
		"FOREIGN KEY (tenant_id, project_id) REFERENCES releasefoundry_projects(tenant_id, project_id)",
		"status IN ('received', 'verified', 'applied', 'failed')",
		"payload_sha256 ~ '^[0-9a-f]{64}$'",
		"releasefoundry_payment_reconciliation_terminal_shape",
	} {
		if !strings.Contains(PaymentReconciliationSchemaSQL, required) {
			t.Fatalf("payment reconciliation schema missing %q", required)
		}
	}
}

func TestMemoryPaymentReconciliationListIsDeterministicBeforeLimit(t *testing.T) {
	service, repository := newPaymentReconciliationTestService(t)
	base := time.Date(2026, 7, 10, 8, 0, 0, 0, time.UTC)
	times := []time.Time{
		base.Add(2 * time.Second),
		base,
		base.Add(time.Second),
	}
	index := 0
	repository.now = func() time.Time {
		value := times[index]
		index++
		return value
	}
	for _, eventID := range []string{"evt_late", "evt_first", "evt_middle"} {
		if _, err := service.Receive(context.Background(), "tenant", "project", PaymentEventHashEnvelope{
			Provider: "stripe", ProviderEventID: eventID, EventType: "checkout.session.completed",
			PayloadSHA256: testPaymentPayloadHash, HeadersSHA256: testPaymentHeadersHash,
		}); err != nil {
			t.Fatal(err)
		}
	}

	for attempt := 0; attempt < 20; attempt++ {
		listed, err := service.List(context.Background(), "tenant", "project", "", 2)
		if err != nil {
			t.Fatal(err)
		}
		got := []string{listed.Result.Events[0].ProviderEventID, listed.Result.Events[1].ProviderEventID}
		want := []string{"evt_first", "evt_middle"}
		if !reflect.DeepEqual(got, want) {
			t.Fatalf("deterministic list attempt %d = %v, want %v", attempt, got, want)
		}
	}
}
