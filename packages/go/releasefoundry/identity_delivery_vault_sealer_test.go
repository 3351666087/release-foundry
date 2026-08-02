package releasefoundry

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

type identityDeliveryAuthenticatedTransport struct {
	base http.RoundTripper
}

func (transport identityDeliveryAuthenticatedTransport) RoundTrip(
	request *http.Request,
) (*http.Response, error) {
	cloned := request.Clone(request.Context())
	cloned.Header = request.Header.Clone()
	cloned.Header.Set("Authorization", "Bearer workload-fixture")
	return transport.base.RoundTrip(cloned)
}

func identityDeliveryVaultSealTestRequest() IdentityDeliverySealRequest {
	return IdentityDeliverySealRequest{
		ReservationID:   "44444444-4444-4444-8444-444444444444",
		TenantID:        "11111111-1111-4111-8111-111111111111",
		ProjectID:       "22222222-2222-4222-8222-222222222222",
		ChallengeHandle: "ivc_444444444444444444444444444444444444",
		Channel:         IdentityVerificationEmail, Purpose: IdentityVerificationLogin,
		Destination: "person@example.test", Code: "123456",
		ExpiresAt: time.Date(2026, 7, 11, 11, 0, 0, 0, time.UTC),
	}
}

func TestHTTPIdentityDeliveryVaultSealerSealsAndDeletesIdempotently(t *testing.T) {
	var deleteCalls atomic.Int32
	server := httptest.NewTLSServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		if request.Header.Get("Authorization") != "Bearer workload-fixture" {
			t.Error("authenticated transport did not authorize vault request")
		}
		switch request.URL.Path {
		case "/seal":
			var payload struct {
				ReservationID   string `json:"reservation_id"`
				ChallengeHandle string `json:"challenge_handle"`
				Destination     string `json:"destination"`
				Code            string `json:"code"`
			}
			if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
				t.Error(err)
			}
			if payload.ReservationID == "" || payload.ChallengeHandle == "" ||
				payload.Destination != "person@example.test" ||
				payload.Code != "123456" {
				t.Error("vault seal payload lost its task binding")
			}
			writer.Header().Set("Content-Type", "application/json")
			writer.WriteHeader(http.StatusCreated)
			_, _ = writer.Write([]byte(`{"opaque_ref":"vault:identity-delivery/sealed-1"}`))
		case "/delete":
			call := deleteCalls.Add(1)
			if call == 1 {
				writer.WriteHeader(http.StatusNoContent)
			} else {
				writer.WriteHeader(http.StatusNotFound)
			}
		default:
			writer.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()
	client := server.Client()
	client.Transport = identityDeliveryAuthenticatedTransport{base: client.Transport}
	sealer, err := NewHTTPIdentityDeliveryVaultSealer(HTTPIdentityDeliveryVaultSealerOptions{
		SealEndpoint: server.URL + "/seal", DeleteEndpoint: server.URL + "/delete",
		Client: client, Timeout: time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	opaqueRef, err := sealer.SealIdentityDelivery(
		context.Background(), identityDeliveryVaultSealTestRequest(),
	)
	if err != nil || opaqueRef != "vault:identity-delivery/sealed-1" {
		t.Fatalf("seal failed: ref=%q err=%v", opaqueRef, err)
	}
	if err := sealer.DeleteIdentityDelivery(context.Background(), opaqueRef); err != nil {
		t.Fatal(err)
	}
	if err := sealer.DeleteIdentityDelivery(context.Background(), opaqueRef); err != nil {
		t.Fatalf("idempotent delete rejected missing payload: %v", err)
	}
}

func TestHTTPIdentityDeliveryVaultSealerRejectsRedirectAndUnsafeResponses(t *testing.T) {
	const secret = "123456"
	var redirected atomic.Int32
	server := httptest.NewTLSServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		switch request.URL.Path {
		case "/redirect":
			http.Redirect(writer, request, "/capture", http.StatusTemporaryRedirect)
		case "/capture":
			redirected.Add(1)
			writer.WriteHeader(http.StatusNoContent)
		case "/unknown-field":
			writer.Header().Set("Content-Type", "application/json")
			_, _ = writer.Write([]byte(`{"opaque_ref":"vault:identity-delivery/sealed-1","secret":"must-reject"}`))
		case "/failure":
			writer.WriteHeader(http.StatusInternalServerError)
			_, _ = writer.Write([]byte(secret))
		default:
			writer.WriteHeader(http.StatusNoContent)
		}
	}))
	defer server.Close()
	request := identityDeliveryVaultSealTestRequest()
	for _, test := range []struct {
		name string
		path string
	}{
		{name: "redirect", path: "/redirect"},
		{name: "unknown response field", path: "/unknown-field"},
		{name: "provider failure", path: "/failure"},
	} {
		t.Run(test.name, func(t *testing.T) {
			sealer, err := NewHTTPIdentityDeliveryVaultSealer(HTTPIdentityDeliveryVaultSealerOptions{
				SealEndpoint: server.URL + test.path, DeleteEndpoint: server.URL + "/delete",
				Client: server.Client(), Timeout: time.Second,
			})
			if err != nil {
				t.Fatal(err)
			}
			_, err = sealer.SealIdentityDelivery(context.Background(), request)
			if err == nil || strings.Contains(err.Error(), secret) {
				t.Fatalf("unsafe vault response was accepted or leaked: %v", err)
			}
		})
	}
	if redirected.Load() != 0 {
		t.Fatal("vault secret-bearing request followed a redirect")
	}
}

func TestHTTPIdentityDeliveryVaultSealerRequiresStrictConfiguration(t *testing.T) {
	client := &http.Client{}
	for _, options := range []HTTPIdentityDeliveryVaultSealerOptions{
		{SealEndpoint: "http://vault.example/seal", DeleteEndpoint: "https://vault.example/delete", Client: client, Timeout: time.Second},
		{SealEndpoint: "https://vault.example/seal", DeleteEndpoint: "http://vault.example/delete", Client: client, Timeout: time.Second},
		{SealEndpoint: "https://vault.example/seal", DeleteEndpoint: "https://vault.example/delete", Timeout: time.Second},
		{SealEndpoint: "https://vault.example/seal", DeleteEndpoint: "https://vault.example/delete", Client: client},
	} {
		if _, err := NewHTTPIdentityDeliveryVaultSealer(options); err == nil {
			t.Fatal("invalid vault sealer configuration was accepted")
		}
	}
	request := identityDeliveryVaultSealTestRequest()
	request.Code = "not-a-code"
	sealer := &HTTPIdentityDeliveryVaultSealer{client: client, timeout: time.Second}
	if _, err := sealer.SealIdentityDelivery(context.Background(), request); err == nil {
		t.Fatal("invalid secret payload was accepted")
	}
	if err := sealer.DeleteIdentityDelivery(
		context.Background(), "vault:unsafe ref",
	); err == nil || errors.Is(err, context.Canceled) {
		t.Fatal("invalid opaque reference was accepted")
	}
}
