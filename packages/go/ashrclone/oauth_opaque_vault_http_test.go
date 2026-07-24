package ashrclone

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

type oauthVaultAuthenticatedTransport struct {
	base http.RoundTripper
}

func (transport oauthVaultAuthenticatedTransport) RoundTrip(request *http.Request) (*http.Response, error) {
	cloned := request.Clone(request.Context())
	cloned.Header = request.Header.Clone()
	cloned.Header.Set("Authorization", "Bearer workload-fixture")
	return transport.base.RoundTrip(cloned)
}

func oauthVaultTestBinding() OAuthSecretBinding {
	return OAuthSecretBinding{
		Provider: "github", TenantID: "11111111-1111-4111-8111-111111111111",
		ProjectID: "22222222-2222-4222-8222-222222222222",
		SessionID: "oauth_first_login:intent-1", UserID: "oauth_first_login:intent-1",
		AccountID: "oauth_first_login:intent-1",
	}
}

func TestHTTPOAuthOpaqueVaultRoundTripAndIdempotentDelete(t *testing.T) {
	binding := oauthVaultTestBinding()
	secret := []byte("provider-token-fixture")
	var deleteCalls atomic.Int32
	server := httptest.NewTLSServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.Header.Get("Authorization") != "Bearer workload-fixture" {
			t.Error("authenticated transport did not authorize OAuth vault request")
		}
		if request.Header.Get("Content-Type") != "application/json" || request.Header.Get("Accept") != "application/json" {
			t.Error("OAuth vault request omitted strict JSON headers")
		}
		switch request.URL.Path {
		case "/put":
			var payload struct {
				Namespace    string             `json:"namespace"`
				Binding      OAuthSecretBinding `json:"binding"`
				SecretBase64 string             `json:"secret_base64"`
			}
			if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
				t.Error(err)
			}
			decoded, err := base64.StdEncoding.DecodeString(payload.SecretBase64)
			if err != nil || string(decoded) != string(secret) || payload.Namespace != "github.oauth.first_login.access_token.v1" || payload.Binding != binding {
				t.Errorf("OAuth vault put payload lost its namespace, binding, or secret")
			}
			writer.Header().Set("Content-Type", "application/json")
			writer.WriteHeader(http.StatusCreated)
			_, _ = writer.Write([]byte(`{"opaque_ref":"vault:oauth/first-login-token-1"}`))
		case "/get":
			writer.Header().Set("Content-Type", "application/json")
			_, _ = writer.Write([]byte(`{"secret_base64":"` + base64.StdEncoding.EncodeToString(secret) + `"}`))
		case "/binding":
			writer.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(writer).Encode(binding)
		case "/delete":
			if deleteCalls.Add(1) == 1 {
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
	client.Transport = oauthVaultAuthenticatedTransport{base: client.Transport}
	vault, err := NewHTTPOAuthOpaqueVault(HTTPOAuthOpaqueVaultOptions{
		PutEndpoint: server.URL + "/put", GetEndpoint: server.URL + "/get",
		BindingEndpoint: server.URL + "/binding", DeleteEndpoint: server.URL + "/delete",
		Client: client, Timeout: time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	ref, err := vault.Put(context.Background(), "github.oauth.first_login.access_token.v1", binding, secret)
	if err != nil || ref != "vault:oauth/first-login-token-1" {
		t.Fatalf("put failed: ref=%q err=%v", ref, err)
	}
	loaded, err := vault.Get(context.Background(), ref)
	if err != nil || string(loaded) != string(secret) {
		t.Fatalf("get failed without exposing secret: len=%d err=%v", len(loaded), err)
	}
	loadedBinding, err := vault.Binding(context.Background(), ref)
	if err != nil || loadedBinding != binding {
		t.Fatalf("binding failed: binding=%#v err=%v", loadedBinding, err)
	}
	if err := vault.Delete(context.Background(), ref); err != nil {
		t.Fatal(err)
	}
	if err := vault.Delete(context.Background(), ref); err != nil {
		t.Fatalf("idempotent delete rejected missing secret: %v", err)
	}
}

func TestHTTPOAuthOpaqueVaultRejectsRedirectUnsafeResponseAndSecretEcho(t *testing.T) {
	const secret = "provider-secret-must-not-leak"
	var redirected atomic.Int32
	server := httptest.NewTLSServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		switch request.URL.Path {
		case "/redirect":
			http.Redirect(writer, request, "/capture", http.StatusTemporaryRedirect)
		case "/capture":
			redirected.Add(1)
			writer.WriteHeader(http.StatusNoContent)
		case "/unknown":
			writer.Header().Set("Content-Type", "application/json")
			_, _ = writer.Write([]byte(`{"opaque_ref":"vault:oauth/ref-1","secret":"must-reject"}`))
		case "/failure":
			writer.WriteHeader(http.StatusInternalServerError)
			_, _ = writer.Write([]byte(secret))
		default:
			writer.WriteHeader(http.StatusNoContent)
		}
	}))
	defer server.Close()
	for _, path := range []string{"/redirect", "/unknown", "/failure"} {
		vault, err := NewHTTPOAuthOpaqueVault(HTTPOAuthOpaqueVaultOptions{
			PutEndpoint: server.URL + path, GetEndpoint: server.URL + "/failure",
			BindingEndpoint: server.URL + "/failure", DeleteEndpoint: server.URL + "/delete",
			Client: server.Client(), Timeout: time.Second,
		})
		if err != nil {
			t.Fatal(err)
		}
		_, err = vault.Put(context.Background(), "github.oauth.first_login.access_token.v1", oauthVaultTestBinding(), []byte(secret))
		if err == nil || strings.Contains(err.Error(), secret) {
			t.Fatalf("unsafe OAuth vault response was accepted or leaked: %v", err)
		}
	}
	if redirected.Load() != 0 {
		t.Fatal("OAuth vault secret-bearing request followed a redirect")
	}
}

func TestHTTPOAuthOpaqueVaultRequiresStrictConfigurationAndBounds(t *testing.T) {
	client := &http.Client{}
	valid := HTTPOAuthOpaqueVaultOptions{
		PutEndpoint: "https://vault.example.test/put", GetEndpoint: "https://vault.example.test/get",
		BindingEndpoint: "https://vault.example.test/binding", DeleteEndpoint: "https://vault.example.test/delete",
		Client: client, Timeout: time.Second,
	}
	for _, mutate := range []func(*HTTPOAuthOpaqueVaultOptions){
		func(options *HTTPOAuthOpaqueVaultOptions) { options.Client = nil },
		func(options *HTTPOAuthOpaqueVaultOptions) { options.PutEndpoint = "http://vault.example.test/put" },
		func(options *HTTPOAuthOpaqueVaultOptions) { options.GetEndpoint += "?query=forbidden" },
		func(options *HTTPOAuthOpaqueVaultOptions) { options.BindingEndpoint = "" },
		func(options *HTTPOAuthOpaqueVaultOptions) { options.Timeout = 0 },
	} {
		options := valid
		mutate(&options)
		if _, err := NewHTTPOAuthOpaqueVault(options); err == nil {
			t.Fatal("invalid OAuth vault configuration was accepted")
		}
	}
	vault, err := NewHTTPOAuthOpaqueVault(valid)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := vault.Put(context.Background(), "unsafe namespace", oauthVaultTestBinding(), []byte("secret")); err == nil {
		t.Fatal("unsafe OAuth vault namespace was accepted")
	}
	if _, err := vault.Put(context.Background(), "github.oauth.first_login.access_token.v1", oauthVaultTestBinding(), make([]byte, maxOAuthOpaqueVaultSecretBytes+1)); err == nil {
		t.Fatal("oversized OAuth vault secret was accepted")
	}
	if _, err := vault.Get(context.Background(), "vault:unsafe ref"); err == nil {
		t.Fatal("unsafe OAuth opaque reference was accepted")
	}
	if err := vault.Delete(nil, "vault:oauth/ref-1"); err == nil || errors.Is(err, context.Canceled) {
		t.Fatal("nil OAuth vault context was accepted")
	}
}
