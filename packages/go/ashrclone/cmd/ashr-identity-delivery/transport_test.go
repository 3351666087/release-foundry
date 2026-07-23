package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/ashr-labs/ashr/packages/go/ashrclone"
)

type identityDeliveryTestRoundTripper func(*http.Request) (*http.Response, error)

func (roundTrip identityDeliveryTestRoundTripper) RoundTrip(
	request *http.Request,
) (*http.Response, error) {
	return roundTrip(request)
}

func TestIdentityDeliveryHTTPClientRejectsRedirectWithoutReplayingSecret(t *testing.T) {
	var targetCalls atomic.Int32
	target := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		targetCalls.Add(1)
		writer.WriteHeader(http.StatusNoContent)
	}))
	defer target.Close()
	redirect := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		http.Redirect(writer, request, target.URL, http.StatusTemporaryRedirect)
	}))
	defer redirect.Close()

	secret := "verification-code-should-not-leak"
	client := &http.Client{
		Timeout: time.Second,
		CheckRedirect: func(*http.Request, []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	defer client.CloseIdleConnections()
	adapter := &identityDeliveryHTTPAdapter{
		endpoint:               redirect.URL,
		channel:                ashrclone.IdentityVerificationEmail,
		client:                 client,
		timeout:                time.Second,
		browserVerificationURL: "https://app.example.test/login/verify",
	}
	err := adapter.SendIdentityVerification(
		context.Background(),
		ashrclone.IdentityVerificationDelivery{
			ChallengeID: "ivc_444444444444444444444444444444444444",
			Channel:     ashrclone.IdentityVerificationEmail, Code: secret,
			Purpose:                ashrclone.IdentityVerificationLogin,
			ProviderIdempotencyKey: "identity-delivery:redirect:0",
		},
	)
	if err == nil {
		t.Fatal("redirect was accepted")
	}
	if targetCalls.Load() != 0 {
		t.Fatalf("secret-bearing request was replayed %d times", targetCalls.Load())
	}
	if strings.Contains(err.Error(), secret) || strings.Contains(err.Error(), target.URL) {
		t.Fatalf("redirect error exposed request details: %q", err)
	}
}

func TestIdentityDeliveryHTTPAdapterEnforcesDeadlineAndCancellation(t *testing.T) {
	release := make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		select {
		case <-request.Context().Done():
		case <-release:
		}
	}))
	defer func() {
		close(release)
		server.Close()
	}()
	adapter := &identityDeliveryHTTPAdapter{
		endpoint: server.URL,
		channel:  ashrclone.IdentityVerificationPhone,
		client:   &http.Client{},
		timeout:  25 * time.Millisecond,
	}
	startedAt := time.Now()
	err := adapter.SendIdentityVerification(
		context.Background(),
		ashrclone.IdentityVerificationDelivery{
			Channel:                ashrclone.IdentityVerificationPhone,
			ProviderIdempotencyKey: "identity-delivery:deadline:0",
		},
	)
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("deadline cause was not preserved: %v", err)
	}
	if elapsed := time.Since(startedAt); elapsed > 250*time.Millisecond {
		t.Fatalf("provider call exceeded bounded deadline: %s", elapsed)
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	err = adapter.SendIdentityVerification(
		ctx,
		ashrclone.IdentityVerificationDelivery{
			Channel:                ashrclone.IdentityVerificationPhone,
			ProviderIdempotencyKey: "identity-delivery:cancel:0",
		},
	)
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("cancellation cause was not preserved: %v", err)
	}
}

func TestIdentityDeliveryHTTPAdapterRedactsTransportFailure(t *testing.T) {
	secret := "tls-private-path-and-provider-secret"
	adapter := &identityDeliveryHTTPAdapter{
		endpoint: "https://relay.internal/v1/send",
		channel:  ashrclone.IdentityVerificationEmail,
		client: &http.Client{
			Transport: identityDeliveryTestRoundTripper(func(
				*http.Request,
			) (*http.Response, error) {
				return nil, errors.New(secret)
			}),
		},
		timeout: time.Second,
	}
	_, err := adapter.SendIdentityVerificationWithAcceptance(
		context.Background(),
		ashrclone.IdentityVerificationDelivery{
			Channel:                ashrclone.IdentityVerificationEmail,
			ProviderIdempotencyKey: "identity-delivery:redaction:0",
		},
	)
	if err == nil || err.Error() != "identity delivery relay is unavailable" ||
		strings.Contains(err.Error(), secret) {
		t.Fatalf("unsafe transport error: %v", err)
	}
}

func TestIdentityDeliveryHTTPAdapterSendsIdempotencyAndParsesAcceptance(t *testing.T) {
	acceptedAt := time.Date(2026, 7, 11, 8, 15, 0, 123, time.UTC)
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		defer request.Body.Close()
		var payload identityDeliveryRelayRequest
		decoder := json.NewDecoder(request.Body)
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&payload); err != nil {
			t.Errorf("decode relay request: %v", err)
			writer.WriteHeader(http.StatusBadRequest)
			return
		}
		if payload.ProviderIdempotencyKey != "identity-delivery:task-1:7" ||
			payload.Channel != ashrclone.IdentityVerificationEmail ||
			payload.Code != "123456" ||
			payload.VerificationURL != "https://app.example.test/login/verify?challenge_id=ivc_444444444444444444444444444444444444&purpose=login" {
			t.Errorf("unexpected relay request: %#v", payload)
		}
		writer.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(writer).Encode(identityDeliveryRelayResponse{
			ProviderAcceptanceRef: "provider-ref:mail/task-1",
			AcceptedAt:            acceptedAt,
		})
	}))
	defer server.Close()
	adapter := &identityDeliveryHTTPAdapter{
		endpoint: server.URL, channel: ashrclone.IdentityVerificationEmail,
		client: server.Client(), timeout: time.Second,
		browserVerificationURL: "https://app.example.test/login/verify",
	}
	acceptance, err := adapter.SendIdentityVerificationWithAcceptance(
		context.Background(),
		ashrclone.IdentityVerificationDelivery{
			ChallengeID: "ivc_444444444444444444444444444444444444",
			Channel:     ashrclone.IdentityVerificationEmail,
			Destination: "user@example.com", Code: "123456",
			Purpose:                ashrclone.IdentityVerificationLogin,
			ExpiresAt:              acceptedAt.Add(time.Minute),
			ProviderIdempotencyKey: "identity-delivery:task-1:7",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if acceptance.Reference != "provider-ref:mail/task-1" ||
		!acceptance.AcceptedAt.Equal(acceptedAt) {
		t.Fatalf("unexpected acceptance: %#v", acceptance)
	}
}

func TestIdentityDeliveryHTTPAdapterRejectsUnsafeAcceptanceResponses(t *testing.T) {
	tests := []struct {
		name        string
		contentType string
		body        string
	}{
		{name: "empty", contentType: "application/json", body: ""},
		{name: "unknown field", contentType: "application/json", body: `{"provider_acceptance_ref":"provider-ref:ok","accepted_at":"2026-07-11T08:15:00Z","provider_payload":"secret"}`},
		{name: "unsafe reference", contentType: "application/json", body: `{"provider_acceptance_ref":"raw-provider-secret value","accepted_at":"2026-07-11T08:15:00Z"}`},
		{name: "missing accepted at", contentType: "application/json", body: `{"provider_acceptance_ref":"provider-ref:ok"}`},
		{name: "oversized", contentType: "application/json", body: strings.Repeat("x", maxIdentityDeliverySidecarResponseBytes+1)},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(
				writer http.ResponseWriter,
				request *http.Request,
			) {
				writer.Header().Set("Content-Type", test.contentType)
				_, _ = writer.Write([]byte(test.body))
			}))
			defer server.Close()
			adapter := &identityDeliveryHTTPAdapter{
				endpoint: server.URL, channel: ashrclone.IdentityVerificationPhone,
				client: server.Client(), timeout: time.Second,
			}
			_, err := adapter.SendIdentityVerificationWithAcceptance(
				context.Background(),
				ashrclone.IdentityVerificationDelivery{
					Channel:                ashrclone.IdentityVerificationPhone,
					ProviderIdempotencyKey: "identity-delivery:strict:0",
				},
			)
			if err == nil || err.Error() != "identity delivery relay is unavailable" {
				t.Fatalf("unexpected error: %v", err)
			}
			if strings.Contains(err.Error(), "provider_payload") ||
				strings.Contains(err.Error(), "raw-provider-secret") {
				t.Fatalf("relay response escaped error boundary: %q", err)
			}
		})
	}
}

func TestIdentityDeliveryHTTPVaultAcceptsStrictJSON(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		writer.Header().Set("Content-Type", "application/json; charset=utf-8")
		_, _ = fmt.Fprintf(
			writer,
			`{"task_id":"task-1","tenant_id":"%s","project_id":"%s",`+
				`"challenge_id":"challenge-1","channel":"email",`+
				`"destination":"user@example.com","code":"123456"}`,
			identityDeliveryTestTenantID,
			identityDeliveryTestProjectID,
		)
	}))
	defer server.Close()
	vault := &identityDeliveryHTTPVault{
		endpoint: server.URL,
		client:   server.Client(),
		timeout:  time.Second,
	}
	defer vault.client.CloseIdleConnections()
	secret, err := vault.OpenIdentityDelivery(context.Background(), "opaque-ref-1")
	if err != nil {
		t.Fatal(err)
	}
	if secret.Code != "123456" || secret.Destination != "user@example.com" ||
		secret.Channel != ashrclone.IdentityVerificationEmail {
		t.Fatalf("unexpected secret envelope: %#v", secret)
	}
}

func TestIdentityDeliveryHTTPVaultRejectsAmbiguousOrOversizedResponses(t *testing.T) {
	valid := fmt.Sprintf(
		`{"task_id":"task-1","tenant_id":"%s","project_id":"%s",`+
			`"challenge_id":"challenge-1","channel":"email",`+
			`"destination":"user@example.com","code":"123456"}`,
		identityDeliveryTestTenantID,
		identityDeliveryTestProjectID,
	)
	tests := []struct {
		name        string
		contentType string
		body        string
	}{
		{name: "wrong content type", contentType: "text/plain", body: valid},
		{name: "trailing JSON", contentType: "application/json", body: valid + `{}`},
		{name: "unknown field", contentType: "application/json", body: strings.TrimSuffix(valid, "}") + `,"secret_hint":"x"}`},
		{name: "oversized", contentType: "application/json", body: strings.Repeat("x", maxIdentityDeliverySidecarResponseBytes+1)},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(
				writer http.ResponseWriter,
				request *http.Request,
			) {
				writer.Header().Set("Content-Type", test.contentType)
				_, _ = writer.Write([]byte(test.body))
			}))
			defer server.Close()
			vault := &identityDeliveryHTTPVault{
				endpoint: server.URL,
				client:   server.Client(),
				timeout:  time.Second,
			}
			defer vault.client.CloseIdleConnections()
			_, err := vault.OpenIdentityDelivery(context.Background(), "opaque-ref-1")
			if err == nil || err.Error() != "identity delivery vault is unavailable" {
				t.Fatalf("unexpected error: %v", err)
			}
			if strings.Contains(err.Error(), "123456") ||
				strings.Contains(err.Error(), "secret_hint") {
				t.Fatalf("response detail escaped error boundary: %q", err)
			}
		})
	}
}

func TestPostIdentityDeliveryJSONRejectsOversizedRequestBeforeNetwork(t *testing.T) {
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		calls.Add(1)
		writer.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()
	err := postIdentityDeliveryJSON(
		context.Background(),
		server.Client(),
		server.URL,
		map[string]string{
			"secret": strings.Repeat("s", maxIdentityDeliverySidecarRequestBytes+1),
		},
		nil,
	)
	if err == nil || calls.Load() != 0 {
		t.Fatalf("oversized request reached network: calls=%d err=%v", calls.Load(), err)
	}
}

func TestIdentityDeliveryMTLSClientFileFailureDoesNotExposePath(t *testing.T) {
	secretPath := "C:/private/identity-delivery/client-key-secret.pem"
	_, err := newIdentityDeliveryMTLSHTTPClient(identityDeliveryMTLSFileProfile{
		caBundleFile: "missing-ca.pem", clientCertificateFile: "missing-cert.pem",
		clientPrivateKeyFile: secretPath, serverName: "relay.internal",
	}, 3*time.Second)
	if err == nil || strings.Contains(err.Error(), secretPath) ||
		strings.Contains(err.Error(), "missing-ca.pem") {
		t.Fatalf("unsafe mTLS file error: %v", err)
	}
}
