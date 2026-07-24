package ashrclone

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

func oauthCredentialResolverReferences() map[string]OAuthCredentialReference {
	return map[string]OAuthCredentialReference{
		"google": {
			ClientIDRef:     "vault:oauth/google-client-id",
			ClientSecretRef: "vault:oauth/google-client-secret",
		},
		"github": {
			ClientIDRef:     "vault:oauth/github-client-id",
			ClientSecretRef: "vault:oauth/github-client-secret",
		},
	}
}

func TestHTTPOAuthCredentialsProviderResolvesByReferenceAndSupportsRotation(t *testing.T) {
	var calls atomic.Int32
	server := httptest.NewTLSServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodPost ||
			request.Header.Get("Content-Type") != "application/json" ||
			request.Header.Get("Accept") != "application/json" {
			t.Fatal("resolver request did not use strict authenticated JSON shape")
		}
		var payload struct {
			Provider        string `json:"provider"`
			Purpose         string `json:"purpose"`
			ClientIDRef     string `json:"client_id_ref"`
			ClientSecretRef string `json:"client_secret_ref"`
		}
		if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
			t.Fatal(err)
		}
		if payload.Purpose != OAuthCredentialResolvePurpose ||
			!ValidOAuthCredentialReference(payload.ClientIDRef) ||
			!ValidOAuthCredentialReference(payload.ClientSecretRef) {
			t.Fatal("resolver request sent an invalid purpose or non-opaque references")
		}
		version := calls.Add(1)
		writer.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(writer).Encode(map[string]string{
			"provider":      payload.Provider,
			"purpose":       OAuthCredentialResolvePurpose,
			"client_id":     payload.Provider + "-client-v" + string(rune('0'+version)),
			"client_secret": payload.Provider + "-secret-v" + string(rune('0'+version)),
		})
	}))
	defer server.Close()
	provider, err := NewHTTPOAuthCredentialsProvider(HTTPOAuthCredentialsProviderOptions{
		Endpoint: server.URL, Client: server.Client(), Timeout: time.Second,
		References: oauthCredentialResolverReferences(),
	})
	if err != nil {
		t.Fatal(err)
	}
	first, err := provider.OAuthCredentials(context.Background(), "google")
	if err != nil || first.ClientID != "google-client-v1" || first.ClientSecret != "google-secret-v1" {
		t.Fatalf("first credential resolution failed: %#v %v", first, err)
	}
	second, err := provider.OAuthCredentials(context.Background(), "google")
	if err != nil || second.ClientID != "google-client-v2" || second.ClientSecret != "google-secret-v2" {
		t.Fatalf("rotated credential resolution failed: %#v %v", second, err)
	}
}

func TestHTTPOAuthCredentialsProviderRejectsUnsafeResponsesAndDoesNotLeakMaterial(t *testing.T) {
	const secret = "secret-manager-response-must-not-leak"
	server := httptest.NewTLSServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		switch request.URL.Path {
		case "/wrong-provider":
			writer.Header().Set("Content-Type", "application/json")
			_, _ = writer.Write([]byte(`{"provider":"github","purpose":"ashr.oauth.client_credentials.v1","client_id":"id","client_secret":"secret"}`))
		case "/wrong-purpose":
			writer.Header().Set("Content-Type", "application/json")
			_, _ = writer.Write([]byte(`{"provider":"google","purpose":"another-purpose","client_id":"id","client_secret":"secret"}`))
		case "/unknown-field":
			writer.Header().Set("Content-Type", "application/json")
			_, _ = writer.Write([]byte(`{"provider":"google","purpose":"ashr.oauth.client_credentials.v1","client_id":"id","client_secret":"secret","raw":"reject"}`))
		case "/trailing-json":
			writer.Header().Set("Content-Type", "application/json")
			_, _ = writer.Write([]byte(`{"provider":"google","purpose":"ashr.oauth.client_credentials.v1","client_id":"id","client_secret":"secret"} {}`))
		case "/wrong-content-type":
			writer.Header().Set("Content-Type", "text/plain")
			_, _ = writer.Write([]byte(`{"provider":"google","purpose":"ashr.oauth.client_credentials.v1","client_id":"id","client_secret":"secret"}`))
		case "/shared-material":
			writer.Header().Set("Content-Type", "application/json")
			_, _ = writer.Write([]byte(`{"provider":"google","purpose":"ashr.oauth.client_credentials.v1","client_id":"same","client_secret":"same"}`))
		case "/oversized":
			writer.Header().Set("Content-Type", "application/json")
			_, _ = writer.Write([]byte(`{"provider":"google","purpose":"ashr.oauth.client_credentials.v1","client_id":"id","client_secret":"`))
			_, _ = writer.Write([]byte(strings.Repeat("S", maxOAuthCredentialResponseBytes)))
			_, _ = writer.Write([]byte(`"}`))
		case "/failure":
			writer.WriteHeader(http.StatusInternalServerError)
			_, _ = writer.Write([]byte(secret))
		default:
			writer.Header().Set("Content-Type", "application/json")
			_, _ = writer.Write([]byte(`{"provider":"google","purpose":"ashr.oauth.client_credentials.v1","client_id":"id","client_secret":"secret"}`))
		}
	}))
	defer server.Close()
	for _, path := range []string{
		"/wrong-provider",
		"/wrong-purpose",
		"/unknown-field",
		"/trailing-json",
		"/wrong-content-type",
		"/shared-material",
		"/oversized",
		"/failure",
	} {
		provider, err := NewHTTPOAuthCredentialsProvider(HTTPOAuthCredentialsProviderOptions{
			Endpoint: server.URL + path, Client: server.Client(), Timeout: time.Second,
			References: oauthCredentialResolverReferences(),
		})
		if err != nil {
			t.Fatal(err)
		}
		_, err = provider.OAuthCredentials(context.Background(), "google")
		if err == nil || strings.Contains(err.Error(), secret) {
			t.Fatalf("unsafe resolver response was accepted or leaked: %v", err)
		}
	}
}

func TestHTTPOAuthCredentialsProviderRejectsRedirectsAndStrictConfiguration(t *testing.T) {
	var redirected atomic.Int32
	server := httptest.NewTLSServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path == "/redirect" {
			http.Redirect(writer, request, "/capture", http.StatusTemporaryRedirect)
			return
		}
		if request.URL.Path == "/capture" {
			redirected.Add(1)
		}
		writer.Header().Set("Content-Type", "application/json")
		_, _ = writer.Write([]byte(`{"provider":"google","purpose":"ashr.oauth.client_credentials.v1","client_id":"id","client_secret":"secret"}`))
	}))
	defer server.Close()
	valid := HTTPOAuthCredentialsProviderOptions{
		Endpoint: server.URL, Client: server.Client(), Timeout: time.Second,
		References: oauthCredentialResolverReferences(),
	}
	for _, mutate := range []func(*HTTPOAuthCredentialsProviderOptions){
		func(options *HTTPOAuthCredentialsProviderOptions) { options.Client = nil },
		func(options *HTTPOAuthCredentialsProviderOptions) {
			options.Endpoint = "http://resolver.example.test/v1"
		},
		func(options *HTTPOAuthCredentialsProviderOptions) { options.Endpoint += "?query=reject" },
		func(options *HTTPOAuthCredentialsProviderOptions) { options.Timeout = 0 },
		func(options *HTTPOAuthCredentialsProviderOptions) {
			options.References = map[string]OAuthCredentialReference{
				"google": {ClientIDRef: "vault:same-ref", ClientSecretRef: "vault:same-ref"},
			}
		},
		func(options *HTTPOAuthCredentialsProviderOptions) {
			options.References = map[string]OAuthCredentialReference{
				"google": {ClientIDRef: "vault:shared-ref", ClientSecretRef: "vault:google-secret"},
				"github": {ClientIDRef: "vault:shared-ref", ClientSecretRef: "vault:github-secret"},
			}
		},
	} {
		options := valid
		mutate(&options)
		if _, err := NewHTTPOAuthCredentialsProvider(options); err == nil {
			t.Fatal("unsafe resolver configuration was accepted")
		}
	}
	provider, err := NewHTTPOAuthCredentialsProvider(HTTPOAuthCredentialsProviderOptions{
		Endpoint: server.URL + "/redirect", Client: server.Client(), Timeout: time.Second,
		References: oauthCredentialResolverReferences(),
	})
	if err != nil {
		t.Fatal(err)
	}
	_, err = provider.OAuthCredentials(context.Background(), "google")
	if err == nil || redirected.Load() != 0 {
		t.Fatalf("resolver followed a redirect or accepted an unsafe response: %v", err)
	}
	if _, err := provider.OAuthCredentials(nil, "google"); err == nil || errors.Is(err, context.Canceled) {
		t.Fatal("nil context was accepted")
	}
	if _, err := provider.OAuthCredentials(context.Background(), "wechat"); err == nil {
		t.Fatal("unconfigured provider was accepted")
	}
}

func TestHTTPOAuthCredentialsProviderPreservesTimeoutAndCancellationCategory(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		time.Sleep(100 * time.Millisecond)
	}))
	defer server.Close()
	provider, err := NewHTTPOAuthCredentialsProvider(HTTPOAuthCredentialsProviderOptions{
		Endpoint: server.URL, Client: server.Client(), Timeout: 20 * time.Millisecond,
		References: oauthCredentialResolverReferences(),
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := provider.OAuthCredentials(context.Background(), "google"); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("resolver timeout category was lost: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := provider.OAuthCredentials(ctx, "google"); !errors.Is(err, context.Canceled) {
		t.Fatalf("resolver cancellation category was lost: %v", err)
	}
}
