package ashrclone

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

type providerDispatchHTTPBackend struct {
	dispatch ProviderDispatch
	claim    ProviderDispatchClaim
	err      error
	action   string
	calls    int
}

func (b *providerDispatchHTTPBackend) SubmitProviderDispatch(_, _, _, _ string, _ JSONMap, _ SubmitProviderDispatchOptions) (Envelope[ProviderDispatch], error) {
	b.calls++
	b.action = "submit"
	return Envelope[ProviderDispatch]{Result: b.dispatch}, b.err
}
func (b *providerDispatchHTTPBackend) ClaimProviderDispatch(_, _, _ string, _ ClaimProviderDispatchOptions) (Envelope[ProviderDispatchClaim], error) {
	b.calls++
	b.action = "claim"
	return Envelope[ProviderDispatchClaim]{Result: b.claim}, b.err
}
func (b *providerDispatchHTTPBackend) ClaimProviderDispatchReconciliation(_, _, _ string, _ ReconcileProviderDispatchOptions) (Envelope[ProviderDispatchClaim], error) {
	b.calls++
	b.action = "reconcile"
	return Envelope[ProviderDispatchClaim]{Result: b.claim}, b.err
}
func (b *providerDispatchHTTPBackend) GetProviderDispatch(_, _, _ string) (Envelope[ProviderDispatch], error) {
	b.calls++
	b.action = "get"
	return Envelope[ProviderDispatch]{Result: b.dispatch}, b.err
}
func (b *providerDispatchHTTPBackend) HeartbeatProviderDispatch(_, _, _, _ string, _ int64, _ int) (Envelope[ProviderDispatch], error) {
	b.calls++
	b.action = "heartbeat"
	return Envelope[ProviderDispatch]{Result: b.dispatch}, b.err
}
func (b *providerDispatchHTTPBackend) ObserveProviderDispatchStream(_, _, _, _ string, _ int64, _ ObserveProviderDispatchStreamOptions) (Envelope[ProviderDispatch], error) {
	b.calls++
	b.action = "observe-stream"
	return Envelope[ProviderDispatch]{Result: b.dispatch}, b.err
}
func (b *providerDispatchHTTPBackend) CompleteProviderDispatch(_, _, _, _ string, _ int64, _ CompleteProviderDispatchOptions) (Envelope[ProviderDispatch], error) {
	b.calls++
	b.action = "complete"
	return Envelope[ProviderDispatch]{Result: b.dispatch}, b.err
}
func (b *providerDispatchHTTPBackend) MarkProviderDispatchIndeterminate(_, _, _, _ string, _ int64, _ string, _ JSONMap, _ time.Time) (Envelope[ProviderDispatch], error) {
	b.calls++
	b.action = "indeterminate"
	return Envelope[ProviderDispatch]{Result: b.dispatch}, b.err
}

func TestProviderDispatchHTTPRoutes(t *testing.T) {
	dispatch := ProviderDispatch{SchemaVersion: ControlPlaneSchemaVersion, TenantID: "tenant", ProjectID: "project", DispatchID: "dispatch", Status: ProviderDispatchClaimed}
	service, secret := providerDispatchHTTPService(t, []string{
		ScopeRunSubmit,
		ScopeRunLifecycleRead,
		ScopeWorkerJobLease,
		ScopeTraceIngest,
		ScopeWorkerJobComplete,
		ScopeWorkerJobFail,
	})
	tests := []struct {
		method, path, body, action string
		status                     int
	}{
		{http.MethodPost, "/v1/tenants/tenant/projects/project/provider-dispatches", `{"provider":"openai","operation":"responses.create","request":{"model":"local"}}`, "submit", http.StatusCreated},
		{http.MethodPost, "/v1/tenants/tenant/projects/project/provider-dispatches/claim", `{"lease_owner_id":"worker"}`, "claim", http.StatusOK},
		{http.MethodPost, "/v1/tenants/tenant/projects/project/provider-dispatches/reconciliation/claim", `{"lease_owner_id":"worker"}`, "reconcile", http.StatusOK},
		{http.MethodGet, "/v1/tenants/tenant/projects/project/provider-dispatches/dispatch", "", "get", http.StatusOK},
		{http.MethodPost, "/v1/tenants/tenant/projects/project/provider-dispatches/dispatch/heartbeat", `{"lease_owner_id":"worker","fencing_token":1}`, "heartbeat", http.StatusOK},
		{http.MethodPost, "/v1/tenants/tenant/projects/project/provider-dispatches/dispatch/observe-stream", `{"lease_owner_id":"worker","fencing_token":1,"stream":{"chunk":"x"}}`, "observe-stream", http.StatusOK},
		{http.MethodPost, "/v1/tenants/tenant/projects/project/provider-dispatches/dispatch/complete", `{"lease_owner_id":"worker","fencing_token":1,"proof":{"chunk":"x"},"response":{"id":"r"}}`, "complete", http.StatusOK},
		{http.MethodPost, "/v1/tenants/tenant/projects/project/provider-dispatches/dispatch/indeterminate", `{"lease_owner_id":"worker","fencing_token":1,"reason":"timeout","failure":{"code":"timeout"}}`, "indeterminate", http.StatusOK},
	}
	for _, test := range tests {
		t.Run(test.action, func(t *testing.T) {
			backend := &providerDispatchHTTPBackend{dispatch: dispatch, claim: ProviderDispatchClaim{SchemaVersion: ControlPlaneSchemaVersion, Status: ProviderDispatchClaimed, Claimed: true, Dispatch: &dispatch}}
			handler := NewHTTPServerWithOptions(service, HTTPServerOptions{ProviderDispatch: backend})
			response := httptest.NewRecorder()
			request := httptest.NewRequest(test.method, test.path, bytes.NewBufferString(test.body))
			request.Header.Set("Authorization", "Bearer "+secret)
			handler.ServeHTTP(response, request)
			if response.Code != test.status || backend.action != test.action {
				t.Fatalf("status=%d action=%q body=%s", response.Code, backend.action, response.Body.String())
			}
			if backend.calls != 1 {
				t.Fatalf("expected exactly one backend call, got %d", backend.calls)
			}
			if strings.Contains(response.Body.String(), `"model":"local"`) {
				t.Fatalf("raw provider request leaked: %s", response.Body.String())
			}
		})
	}
}

func TestProviderDispatchHTTPUsesStableSafeErrors(t *testing.T) {
	service, secret := providerDispatchHTTPService(t, []string{ScopeRunLifecycleRead})
	tests := []struct {
		err  error
		code string
		http int
	}{
		{sql.ErrNoRows, "provider_dispatch_not_found", http.StatusNotFound},
		{ErrProviderDispatchConflict, "provider_dispatch_conflict", http.StatusConflict},
		{ErrProviderDispatchFence, "provider_dispatch_fence", http.StatusConflict},
		{ErrProviderDispatchCancelled, "provider_dispatch_cancelled", http.StatusRequestTimeout},
		{ErrProviderDispatchDeadline, "provider_dispatch_deadline", http.StatusGatewayTimeout},
		{ErrProviderDispatchContention, "provider_dispatch_contention", http.StatusConflict},
		{ErrProviderDispatchIndeterminate, "provider_dispatch_indeterminate", http.StatusServiceUnavailable},
		{errors.New("pq: password=secret host=private table=ashr_provider_dispatches"), "provider_dispatch_unavailable", http.StatusServiceUnavailable},
	}
	for _, test := range tests {
		t.Run(test.code, func(t *testing.T) {
			backend := &providerDispatchHTTPBackend{err: test.err}
			handler := NewHTTPServerWithOptions(service, HTTPServerOptions{ProviderDispatch: backend})
			response := httptest.NewRecorder()
			request := httptest.NewRequest(http.MethodGet, "/v1/tenants/tenant/projects/project/provider-dispatches/dispatch", nil)
			request.Header.Set("Authorization", "Bearer "+secret)
			handler.ServeHTTP(response, request)
			if response.Code != test.http {
				t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
			}
			var payload JSONMap
			if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
				t.Fatal(err)
			}
			errorPayload, _ := payload["error"].(map[string]any)
			if errorPayload["code"] != test.code {
				t.Fatalf("expected %q: %#v", test.code, payload)
			}
			for _, secret := range []string{"password", "private", "ashr_provider_dispatches", "pq:"} {
				if strings.Contains(response.Body.String(), secret) {
					t.Fatalf("sensitive backend detail leaked: %s", response.Body.String())
				}
			}
		})
	}
}

func TestProviderDispatchHTTPDenialsDoNotTouchBackend(t *testing.T) {
	const path = "/v1/tenants/tenant/projects/project/provider-dispatches"
	tests := []struct {
		name       string
		scopes     []string
		path       string
		secretMode string
		headers    map[string]string
		rateLimit  *int
		status     int
		code       string
	}{
		{name: "missing auth", scopes: []string{ScopeRunSubmit}, secretMode: "missing", status: http.StatusUnauthorized, code: "authentication_required"},
		{name: "wrong scope", scopes: []string{ScopeRunLifecycleRead}, secretMode: "handle", status: http.StatusForbidden, code: "scope_denied"},
		{name: "tenant mismatch", scopes: []string{ScopeRunSubmit}, secretMode: "valid", headers: map[string]string{"X-Ashr-Tenant-ID": "other"}, status: http.StatusForbidden, code: "tenant_mismatch"},
		{name: "api key mismatch", scopes: []string{ScopeRunSubmit}, secretMode: "valid", headers: map[string]string{"X-Ashr-API-Key-ID": "other"}, status: http.StatusForbidden, code: "api_key_mismatch"},
		{name: "invalid bearer", scopes: []string{ScopeRunSubmit}, secretMode: "invalid", status: http.StatusForbidden, code: "secret_input_rejected"},
		{name: "quota denial", scopes: []string{ScopeRunSubmit}, secretMode: "valid", rateLimit: intPointer(0), status: http.StatusTooManyRequests, code: "quota_exceeded"},
		{name: "unknown route", scopes: []string{ScopeRunSubmit}, path: path + "/unknown/operation", secretMode: "valid", status: http.StatusNotFound, code: "not_found"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			service, secret := providerDispatchHTTPService(t, test.scopes)
			if test.rateLimit != nil {
				if _, err := service.ConfigureAPIKeyRateLimit("tenant", "project", "key_dispatch", "provider_dispatch.submit", *test.rateLimit); err != nil {
					t.Fatal(err)
				}
			}
			backend := &providerDispatchHTTPBackend{}
			handler := NewHTTPServerWithOptions(service, HTTPServerOptions{ProviderDispatch: backend})
			target := test.path
			if target == "" {
				target = path
			}
			request := httptest.NewRequest(http.MethodPost, target, bytes.NewBufferString(`{"provider":"openai","operation":"responses.create","request":{"model":"local"}}`))
			switch test.secretMode {
			case "valid":
				request.Header.Set("Authorization", "Bearer "+secret)
			case "handle":
				request.Header.Set("X-Ashr-Tenant-ID", "tenant")
				request.Header.Set("X-Ashr-API-Key-ID", "key_dispatch")
			case "invalid":
				request.Header.Set("Authorization", "Bearer sk_local_key_dispatch_invalid")
			}
			for name, value := range test.headers {
				request.Header.Set(name, value)
			}
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != test.status {
				t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
			}
			var payload struct {
				Error struct {
					Code string `json:"code"`
				} `json:"error"`
			}
			if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
				t.Fatal(err)
			}
			if payload.Error.Code != test.code {
				t.Fatalf("expected error %q, got %#v", test.code, payload)
			}
			if backend.calls != 0 {
				t.Fatalf("denied request reached provider dispatch backend %d time(s)", backend.calls)
			}
		})
	}
}

func providerDispatchHTTPService(t *testing.T, scopes []string) (*MemoryService, string) {
	t.Helper()
	service := NewMemoryService()
	if _, err := service.BootstrapProject("Tenant", "Project", Dataset{Name: "Dataset"}, "tenant", "project"); err != nil {
		t.Fatal(err)
	}
	created, err := service.CreateAPIKey("tenant", "project", CreateAPIKeyOptions{
		KeyID: "key_dispatch", Name: "Provider dispatch", Scopes: scopes, RevealSecret: true,
	})
	if err != nil {
		t.Fatal(err)
	}
	return service, created.Result.OneTimeSecret
}

func intPointer(value int) *int {
	return &value
}
