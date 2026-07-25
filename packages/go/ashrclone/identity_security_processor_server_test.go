package ashrclone

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

type identitySecurityProcessorTestReadiness struct {
	mu    sync.Mutex
	calls int
	err   error
}

func (readiness *identitySecurityProcessorTestReadiness) Ready(
	context.Context,
) error {
	readiness.mu.Lock()
	defer readiness.mu.Unlock()
	readiness.calls++
	return readiness.err
}

func (readiness *identitySecurityProcessorTestReadiness) callCount() int {
	readiness.mu.Lock()
	defer readiness.mu.Unlock()
	return readiness.calls
}

func TestIdentitySecurityProcessorHandlerAndHTTPClientRoundTrip(t *testing.T) {
	processor, _, _, _ := newIdentitySecurityProcessorVaultTestSubject(t)
	readiness := &identitySecurityProcessorTestReadiness{}
	handler, err := NewIdentitySecurityProcessorHandler(
		IdentitySecurityProcessorHandlerOptions{
			Processor:        processor,
			Readiness:        readiness,
			ReadinessTimeout: time.Second,
		},
	)
	if err != nil {
		t.Fatalf("new processor handler: %v", err)
	}
	server := httptest.NewTLSServer(handler)
	defer server.Close()
	client, err := NewHTTPIdentitySecuritySecretProcessor(
		HTTPIdentitySecuritySecretProcessorOptions{
			ProcessEndpoint: server.URL + "/v1/identity/security/process",
			ConfirmEndpoint: server.URL + "/v1/identity/security/confirm",
			HandoffConsumeEndpoint: server.URL +
				"/v1/identity/security/handoff/consume",
			CleanupEndpoint: server.URL + "/v1/identity/security/cleanup",
			Client:          server.Client(),
			Timeout:         time.Second,
		},
	)
	if err != nil {
		t.Fatalf("new processor HTTP client: %v", err)
	}
	request := IdentitySecuritySecretProcessRequest{
		AccountID:      identitySecurityProcessorVaultTestAccountID,
		Operation:      "password_enroll",
		IdempotencyKey: "handler-password-0001",
		Password:       "correct horse battery staple",
	}
	processed, err := client.ProcessIdentitySecuritySecret(
		context.Background(),
		request,
	)
	if err != nil || !validIdentitySecuritySecretProcessResult(
		request.Operation,
		processed,
	) {
		t.Fatalf("processor HTTP round trip: result=%+v err=%v", processed, err)
	}
	if err := client.CleanupIdentitySecuritySecret(
		context.Background(),
		IdentitySecuritySecretCleanupRequest{
			AccountID:      request.AccountID,
			Operation:      request.Operation,
			IdempotencyKey: request.IdempotencyKey,
			CleanupToken:   processed.CleanupToken,
		},
	); err != nil {
		t.Fatalf("processor HTTP cleanup: %v", err)
	}
	for _, path := range []string{"/health", "/ready"} {
		response, err := server.Client().Get(server.URL + path)
		if err != nil {
			t.Fatalf("GET %s: %v", path, err)
		}
		if response.StatusCode != http.StatusOK {
			response.Body.Close()
			t.Fatalf("GET %s returned %d", path, response.StatusCode)
		}
		assertIdentitySecurityProcessorNoStore(t, response)
		response.Body.Close()
	}
	if readiness.callCount() != 1 {
		t.Fatalf("health endpoint read secret readiness state")
	}
}

func TestIdentitySecurityProcessorHandlerStrictRequestAndStableErrors(t *testing.T) {
	processor, vault, _, _ := newIdentitySecurityProcessorVaultTestSubject(t)
	readiness := &identitySecurityProcessorTestReadiness{}
	handler, err := NewIdentitySecurityProcessorHandler(
		IdentitySecurityProcessorHandlerOptions{
			Processor:        processor,
			Readiness:        readiness,
			ReadinessTimeout: time.Second,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(handler)
	defer server.Close()
	valid := map[string]any{
		"schema_version":  IdentitySecurityProcessorSchemaVersion,
		"account_id":      identitySecurityProcessorVaultTestAccountID,
		"operation":       "password_enroll",
		"idempotency_key": "handler-strict-0001",
		"password":        "correct horse battery staple",
	}
	testCases := []struct {
		name        string
		contentType string
		body        []byte
		status      int
	}{
		{
			name:        "wrong content type",
			contentType: "text/plain",
			body:        mustIdentitySecurityProcessorTestJSON(t, valid),
			status:      http.StatusBadRequest,
		},
		{
			name:        "unknown field",
			contentType: "application/json",
			body: []byte(`{"schema_version":"ashr.identity_security_processor.v1",` +
				`"account_id":"33333333-3333-4333-8333-333333333333",` +
				`"operation":"password_enroll","idempotency_key":"handler-strict-0001",` +
				`"password":"correct horse battery staple","secret_ref":"forbidden"}`),
			status: http.StatusBadRequest,
		},
		{
			name:        "trailing JSON",
			contentType: "application/json",
			body: append(
				mustIdentitySecurityProcessorTestJSON(t, valid),
				[]byte(`{}`)...,
			),
			status: http.StatusBadRequest,
		},
		{
			name:        "wrong schema",
			contentType: "application/json",
			body: []byte(`{"schema_version":"wrong","account_id":` +
				`"33333333-3333-4333-8333-333333333333","operation":` +
				`"password_enroll","idempotency_key":"handler-strict-0001",` +
				`"password":"correct horse battery staple"}`),
			status: http.StatusBadRequest,
		},
		{
			name:        "processor rejection",
			contentType: "application/json",
			body: []byte(`{"schema_version":"ashr.identity_security_processor.v1",` +
				`"account_id":"33333333-3333-4333-8333-333333333333",` +
				`"operation":"password_enroll","idempotency_key":"handler-strict-0001",` +
				`"password":"too-short"}`),
			status: http.StatusForbidden,
		},
		{
			name:        "oversized",
			contentType: "application/json",
			body:        bytes.Repeat([]byte("x"), maxIdentitySecurityProcessorRequestBytes+1),
			status:      http.StatusBadRequest,
		},
	}
	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			response := postIdentitySecurityProcessorTestRequest(
				t,
				server.URL+"/v1/identity/security/process",
				testCase.contentType,
				testCase.body,
			)
			defer response.Body.Close()
			if response.StatusCode != testCase.status {
				t.Fatalf("status=%d want=%d", response.StatusCode, testCase.status)
			}
			assertIdentitySecurityProcessorNoStore(t, response)
			body, err := io.ReadAll(response.Body)
			if err != nil {
				t.Fatal(err)
			}
			if bytes.Contains(body, []byte("correct horse battery staple")) ||
				bytes.Contains(body, []byte("secret_ref")) {
				t.Fatalf("stable error reflected secret-bearing input")
			}
		})
	}

	const secretMarker = "vault-upstream-secret-must-not-leak"
	vault.createErr = errors.New(secretMarker)
	unavailable := valid
	unavailable["idempotency_key"] = "handler-unavailable-0001"
	response := postIdentitySecurityProcessorTestRequest(
		t,
		server.URL+"/v1/identity/security/process",
		"application/json",
		mustIdentitySecurityProcessorTestJSON(t, unavailable),
	)
	defer response.Body.Close()
	if response.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("unavailable status=%d", response.StatusCode)
	}
	body, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(body, []byte(secretMarker)) {
		t.Fatalf("processor error reflected upstream secret")
	}

	readiness.err = errors.New(secretMarker)
	readyResponse, err := http.Get(server.URL + "/ready")
	if err != nil {
		t.Fatal(err)
	}
	defer readyResponse.Body.Close()
	if readyResponse.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("unready status=%d", readyResponse.StatusCode)
	}
	readyBody, err := io.ReadAll(readyResponse.Body)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(readyBody), secretMarker) {
		t.Fatalf("readiness response exposed internal error")
	}
}

func TestIdentitySecurityProcessorHandlerConfiguration(t *testing.T) {
	processor, _, _, _ := newIdentitySecurityProcessorVaultTestSubject(t)
	for _, options := range []IdentitySecurityProcessorHandlerOptions{
		{},
		{Processor: processor, ReadinessTimeout: time.Second},
		{
			Processor:        processor,
			Readiness:        processor,
			ReadinessTimeout: 0,
		},
	} {
		if _, err := NewIdentitySecurityProcessorHandler(options); err == nil {
			t.Fatalf("invalid processor handler configuration was accepted")
		}
	}
}

func postIdentitySecurityProcessorTestRequest(
	t *testing.T,
	endpoint string,
	contentType string,
	body []byte,
) *http.Response {
	t.Helper()
	request, err := http.NewRequest(
		http.MethodPost,
		endpoint,
		bytes.NewReader(body),
	)
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("Content-Type", contentType)
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	return response
}

func mustIdentitySecurityProcessorTestJSON(t *testing.T, value any) []byte {
	t.Helper()
	encoded, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return encoded
}

func assertIdentitySecurityProcessorNoStore(
	t *testing.T,
	response *http.Response,
) {
	t.Helper()
	if response.Header.Get("Cache-Control") != "no-store" ||
		response.Header.Get("Pragma") != "no-cache" {
		t.Fatalf("processor response omitted no-store headers")
	}
}

var _ IdentitySecurityProcessorReadiness = (*identitySecurityProcessorTestReadiness)(
	nil,
)
