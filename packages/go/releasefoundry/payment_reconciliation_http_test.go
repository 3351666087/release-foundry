package releasefoundry

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"reflect"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"
)

type paymentReconciliationHTTPFixture struct {
	service        *MemoryService
	reconciliation *PaymentReconciliationService
	repository     *MemoryPaymentReconciliationRepository
	server         *httptest.Server
}

func newPaymentReconciliationHTTPFixture(t *testing.T) paymentReconciliationHTTPFixture {
	t.Helper()
	service := NewMemoryService()
	if _, err := service.BootstrapProject("Tenant", "Payments", Dataset{Name: "Payments"}, "tenant_payments", "project_payments"); err != nil {
		t.Fatal(err)
	}
	for _, key := range []struct {
		id     string
		scopes []string
	}{
		{id: "key_payment_receive", scopes: []string{ScopeBillingWebhookIngest}},
		{id: "key_payment_read", scopes: []string{ScopeBillingRead}},
		{id: "key_payment_all", scopes: []string{ScopeBillingWebhookIngest, ScopeBillingRead}},
		{id: "key_payment_wrong", scopes: []string{ScopeRunSubmit}},
	} {
		if _, err := service.CreateAPIKey("tenant_payments", "project_payments", CreateAPIKeyOptions{KeyID: key.id, Name: key.id, Scopes: key.scopes}); err != nil {
			t.Fatal(err)
		}
	}
	repository := NewMemoryPaymentReconciliationRepository()
	now := time.Date(2026, 7, 10, 9, 0, 0, 0, time.UTC)
	repository.now = func() time.Time {
		now = now.Add(time.Second)
		return now
	}
	reconciliation, err := NewPaymentReconciliationService(repository)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(NewHTTPServerWithOptions(service, HTTPServerOptions{
		BackendName:           "memory_service_v0",
		BackendReady:          true,
		PaymentReconciliation: reconciliation,
	}))
	t.Cleanup(server.Close)
	return paymentReconciliationHTTPFixture{service: service, reconciliation: reconciliation, repository: repository, server: server}
}

func paymentReconciliationURL(serverURL, projectID string) string {
	return serverURL + "/v1/projects/" + projectID + "/billing/reconciliation/events"
}

func paymentReconciliationAuthRequest(t *testing.T, method, url, tenantID, keyID string, payload any) *http.Request {
	t.Helper()
	return authenticatedRequestForTest(t, method, url, payload, tenantID, keyID)
}

func paymentReconciliationEnvelope(eventID string) JSONMap {
	return JSONMap{
		"provider":          "stripe",
		"provider_event_id": eventID,
		"event_type":        "checkout.session.completed",
		"payload_sha256":    testPaymentPayloadHash,
		"headers_sha256":    testPaymentHeadersHash,
	}
}

func TestPaymentReconciliationHTTPRequiresConfiguredCapability(t *testing.T) {
	service := NewMemoryService()
	if _, err := service.BootstrapProject("Tenant", "Payments", Dataset{Name: "Payments"}, "tenant_payments", "project_payments"); err != nil {
		t.Fatal(err)
	}
	if _, err := service.CreateAPIKey("tenant_payments", "project_payments", CreateAPIKeyOptions{KeyID: "key_payment", Name: "Payment", Scopes: []string{ScopeBillingWebhookIngest}}); err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(NewHTTPServerWithOptions(service, HTTPServerOptions{BackendName: "memory_service_v0", BackendReady: true}))
	defer server.Close()

	assertControlPlaneError(
		t,
		paymentReconciliationAuthRequest(t, http.MethodPost, paymentReconciliationURL(server.URL, "project_payments"), "tenant_payments", "key_payment", paymentReconciliationEnvelope("evt_unavailable")),
		http.StatusServiceUnavailable,
		"payment_reconciliation_unavailable",
	)
}

func TestPaymentReconciliationHTTPReceiveReplayConflictGetAndList(t *testing.T) {
	fixture := newPaymentReconciliationHTTPFixture(t)
	baseURL := paymentReconciliationURL(fixture.server.URL, "project_payments")

	received := doJSONForTest[PaymentReconciliationEvent](t, paymentReconciliationAuthRequest(
		t, http.MethodPost, baseURL, "tenant_payments", "key_payment_receive", paymentReconciliationEnvelope("evt_http"),
	), http.StatusOK)
	if received.Status != PaymentEventStatusReceived || received.Provider != "stripe" || received.ProviderEventID != "evt_http" {
		t.Fatalf("unexpected received event: %#v", received)
	}

	replayed := doJSONForTest[PaymentReconciliationEvent](t, paymentReconciliationAuthRequest(
		t, http.MethodPost, baseURL, "tenant_payments", "key_payment_receive", paymentReconciliationEnvelope("evt_http"),
	), http.StatusOK)
	if !reflect.DeepEqual(received, replayed) {
		t.Fatalf("HTTP replay changed state: first=%#v replay=%#v", received, replayed)
	}
	listed := doJSONForTest[PaymentReconciliationList](t, paymentReconciliationAuthRequest(
		t, http.MethodGet, baseURL+"?tenant_id=tenant_payments&auth_key_id=key_payment_read", "tenant_payments", "key_payment_read", nil,
	), http.StatusOK)
	if listed.Count != 1 || len(listed.Events) != 1 || listed.Events[0].ProviderEventID != "evt_http" {
		t.Fatalf("duplicate receive created extra state: %#v", listed)
	}

	conflict := paymentReconciliationEnvelope("evt_http")
	conflict["payload_sha256"] = testPaymentHeadersHash
	assertControlPlaneError(
		t,
		paymentReconciliationAuthRequest(t, http.MethodPost, baseURL, "tenant_payments", "key_payment_receive", conflict),
		http.StatusConflict,
		"payment_reconciliation_conflict",
	)

	got := doJSONForTest[PaymentReconciliationEvent](t, paymentReconciliationAuthRequest(
		t, http.MethodGet, baseURL+"/stripe/evt_http?tenant_id=tenant_payments&auth_key_id=key_payment_read", "tenant_payments", "key_payment_read", nil,
	), http.StatusOK)
	if !reflect.DeepEqual(received, got) {
		t.Fatalf("get differs from received state: received=%#v got=%#v", received, got)
	}
}

func TestPaymentReconciliationHTTPFilteringLimitOrderingAndIsolation(t *testing.T) {
	fixture := newPaymentReconciliationHTTPFixture(t)
	baseURL := paymentReconciliationURL(fixture.server.URL, "project_payments")
	for _, eventID := range []string{"evt_first", "evt_second", "evt_third"} {
		doJSONForTest[PaymentReconciliationEvent](t, paymentReconciliationAuthRequest(
			t, http.MethodPost, baseURL, "tenant_payments", "key_payment_receive", paymentReconciliationEnvelope(eventID),
		), http.StatusOK)
	}
	if _, err := fixture.reconciliation.Verify(context.Background(), "tenant_payments", "project_payments", "stripe", "evt_second"); err != nil {
		t.Fatal(err)
	}

	filtered := doJSONForTest[PaymentReconciliationList](t, paymentReconciliationAuthRequest(
		t, http.MethodGet, baseURL+"?tenant_id=tenant_payments&auth_key_id=key_payment_read&status=verified&limit=1", "tenant_payments", "key_payment_read", nil,
	), http.StatusOK)
	if filtered.Count != 1 || filtered.Status != PaymentEventStatusVerified || filtered.Events[0].ProviderEventID != "evt_second" {
		t.Fatalf("unexpected filtered result: %#v", filtered)
	}
	limited := doJSONForTest[PaymentReconciliationList](t, paymentReconciliationAuthRequest(
		t, http.MethodGet, baseURL+"?tenant_id=tenant_payments&auth_key_id=key_payment_read&limit=2", "tenant_payments", "key_payment_read", nil,
	), http.StatusOK)
	gotIDs := []string{limited.Events[0].ProviderEventID, limited.Events[1].ProviderEventID}
	if want := []string{"evt_first", "evt_second"}; !reflect.DeepEqual(gotIDs, want) {
		t.Fatalf("deterministic ordering = %v, want %v", gotIDs, want)
	}

	assertControlPlaneError(
		t,
		paymentReconciliationAuthRequest(t, http.MethodGet, baseURL+"?tenant_id=tenant_other&auth_key_id=key_payment_read", "tenant_payments", "key_payment_read", nil),
		http.StatusForbidden,
		"tenant_mismatch",
	)
	assertControlPlaneError(
		t,
		paymentReconciliationAuthRequest(t, http.MethodGet, paymentReconciliationURL(fixture.server.URL, "project_other")+"?tenant_id=tenant_payments&auth_key_id=key_payment_read", "tenant_payments", "key_payment_read", nil),
		http.StatusForbidden,
		"api_key_not_found",
	)
}

func TestPaymentReconciliationHTTPRejectsMissingAndWrongScopes(t *testing.T) {
	fixture := newPaymentReconciliationHTTPFixture(t)
	baseURL := paymentReconciliationURL(fixture.server.URL, "project_payments")

	assertControlPlaneError(t, requestForTest(t, http.MethodPost, baseURL, paymentReconciliationEnvelope("evt_missing")), http.StatusUnauthorized, "authentication_required")
	assertControlPlaneError(
		t,
		paymentReconciliationAuthRequest(t, http.MethodPost, baseURL, "tenant_payments", "key_payment_read", paymentReconciliationEnvelope("evt_wrong_receive")),
		http.StatusForbidden,
		"scope_denied",
	)
	assertControlPlaneError(
		t,
		paymentReconciliationAuthRequest(t, http.MethodGet, baseURL+"?tenant_id=tenant_payments&auth_key_id=key_payment_receive", "tenant_payments", "key_payment_receive", nil),
		http.StatusForbidden,
		"scope_denied",
	)
	assertControlPlaneError(
		t,
		paymentReconciliationAuthRequest(t, http.MethodGet, baseURL+"?tenant_id=tenant_payments&auth_key_id=key_payment_wrong", "tenant_payments", "key_payment_wrong", nil),
		http.StatusForbidden,
		"scope_denied",
	)
}

func TestPaymentReconciliationHTTPOutputIsPublicSafe(t *testing.T) {
	fixture := newPaymentReconciliationHTTPFixture(t)
	baseURL := paymentReconciliationURL(fixture.server.URL, "project_payments")
	event := doJSONForTest[PaymentReconciliationEvent](t, paymentReconciliationAuthRequest(
		t, http.MethodPost, baseURL, "tenant_payments", "key_payment_receive", paymentReconciliationEnvelope("evt_public_safe"),
	), http.StatusOK)
	encoded, err := json.Marshal(event)
	if err != nil {
		t.Fatal(err)
	}
	serialized := strings.ToLower(string(encoded))
	for _, forbidden := range []string{
		`"raw_payload"`, `"raw_header"`, `"signature"`, `"webhook_secret"`,
		`"authorization"`, `"card_number"`, `"pan"`, `"cvc"`, `"cvv"`,
	} {
		if strings.Contains(serialized, forbidden) {
			t.Fatalf("public reconciliation output contains forbidden field %q: %s", forbidden, serialized)
		}
	}
	if event.RawPayloadIncluded || event.RawHeadersIncluded || event.SecretValuePresent {
		t.Fatalf("public safety flags were not false: %#v", event)
	}
}

func TestPaymentReconciliationHTTPTransitionRoutesAreNotPublic(t *testing.T) {
	fixture := newPaymentReconciliationHTTPFixture(t)
	baseURL := paymentReconciliationURL(fixture.server.URL, "project_payments")
	doJSONForTest[PaymentReconciliationEvent](t, paymentReconciliationAuthRequest(
		t, http.MethodPost, baseURL, "tenant_payments", "key_payment_receive", paymentReconciliationEnvelope("evt_internal_only"),
	), http.StatusOK)

	for _, transition := range []string{"verify", "apply", "fail"} {
		assertControlPlaneError(
			t,
			paymentReconciliationAuthRequest(t, http.MethodPost, baseURL+"/stripe/evt_internal_only/"+transition, "tenant_payments", "key_payment_all", JSONMap{"failure_sha256": testPaymentFailureHash}),
			http.StatusNotFound,
			"not_found",
		)
	}
}

func TestPaymentReconciliationManifestAndHostedClientExposeSafeSurfaceOnly(t *testing.T) {
	want := map[string]string{
		"POST /v1/projects/{project_id}/billing/reconciliation/events":                      ScopeBillingWebhookIngest,
		"GET /v1/projects/{project_id}/billing/reconciliation/events":                       ScopeBillingRead,
		"GET /v1/projects/{project_id}/billing/reconciliation/events/{provider}/{event_id}": ScopeBillingRead,
	}
	found := map[string]bool{}
	for _, route := range GoRouteManifestEntries() {
		if strings.Contains(route.Path, "/billing/reconciliation/") {
			scope, ok := want[route.Route]
			if !ok {
				t.Fatalf("manifest exposes unsafe reconciliation route: %#v", route)
			}
			if len(route.Scopes) != 1 || route.Scopes[0] != scope || !route.AuthRequired || !route.PublicSafe {
				t.Fatalf("unsafe reconciliation route metadata: %#v", route)
			}
			found[route.Route] = true
		}
	}
	if len(found) != len(want) {
		t.Fatalf("manifest reconciliation routes = %#v, want %#v", found, want)
	}

	clientType := reflect.TypeOf(&Client{})
	methods := []string{}
	for index := 0; index < clientType.NumMethod(); index++ {
		methods = append(methods, clientType.Method(index).Name)
	}
	sort.Strings(methods)
	for _, required := range []string{"ReceivePaymentReconciliationHTTP", "ListPaymentReconciliationHTTP", "GetPaymentReconciliationHTTP"} {
		if _, ok := clientType.MethodByName(required); !ok {
			t.Fatalf("hosted client missing %s", required)
		}
	}
	for _, forbidden := range []string{"VerifyPaymentReconciliationHTTP", "ApplyPaymentReconciliationHTTP", "FailPaymentReconciliationHTTP"} {
		if _, ok := clientType.MethodByName(forbidden); ok {
			t.Fatalf("hosted client exposes internal transition %s; methods=%v", forbidden, methods)
		}
	}
}

func TestBillingWebhookUnverifiedConcurrencyHasZeroSideEffects(t *testing.T) {
	service := NewMemoryService()
	if _, err := service.BootstrapProject("Tenant", "Billing", Dataset{Name: "Billing"}, "tenant_billing_atomic", "project_billing_atomic"); err != nil {
		t.Fatal(err)
	}
	event := BillingWebhookIngest{
		EventID: "evt_atomic", EventType: "checkout.session.completed", Provider: "stripe",
		Mode: "test", PlanID: "startup", Status: "active", PayloadSHA256: testPaymentPayloadHash,
		SignatureHeaderPresent: true, WebhookSecretRef: "env:STRIPE_WEBHOOK_SECRET",
	}
	const callers = 32
	start := make(chan struct{})
	errs := make(chan error, callers)
	statuses := make(chan string, callers)
	var wait sync.WaitGroup
	for index := 0; index < callers; index++ {
		wait.Add(1)
		go func() {
			defer wait.Done()
			<-start
			result, err := service.IngestBillingWebhook("tenant_billing_atomic", "project_billing_atomic", event, IdempotencyOptions{Key: "idem_atomic"})
			errs <- err
			statuses <- result.Status
		}()
	}
	close(start)
	wait.Wait()
	close(errs)
	close(statuses)
	for err := range errs {
		if err != nil {
			t.Fatalf("concurrent webhook ingest failed: %v", err)
		}
	}
	for status := range statuses {
		if status != "rejected" {
			t.Fatalf("unverified webhook status = %q, want rejected", status)
		}
	}
	service.mu.Lock()
	defer service.mu.Unlock()
	if len(service.billingEvents) != 0 {
		t.Fatalf("unverified webhook mutated billing ledger: %#v", service.billingEvents)
	}
	if len(service.idem) != 0 {
		t.Fatalf("unverified webhook mutated idempotency ledger: %#v", service.idem)
	}
}

func TestBillingWebhookCallerVerifiedFlagCannotCreateIdempotencyState(t *testing.T) {
	service := NewMemoryService()
	if _, err := service.BootstrapProject("Tenant", "Billing", Dataset{Name: "Billing"}, "tenant_billing_conflict", "project_billing_conflict"); err != nil {
		t.Fatal(err)
	}
	first := BillingWebhookIngest{EventID: "evt_first", EventType: "invoice.paid", Provider: "stripe", Mode: "test", Status: "active", PayloadSHA256: testPaymentPayloadHash, Verified: true, SignatureHeaderPresent: true, WebhookSecretRef: "env:STRIPE_WEBHOOK_SECRET"}
	response, err := service.IngestBillingWebhook("tenant_billing_conflict", "project_billing_conflict", first, IdempotencyOptions{Key: "idem_conflict"})
	if err != nil {
		t.Fatal(err)
	}
	if response.Status != "rejected" || response.Result.Verified {
		t.Fatalf("caller asserted verification was trusted: %#v", response)
	}
	service.mu.Lock()
	defer service.mu.Unlock()
	if len(service.billingEvents) != 0 || len(service.idem) != 0 {
		t.Fatalf("caller asserted verification mutated state: events=%#v idem=%#v", service.billingEvents, service.idem)
	}
}
