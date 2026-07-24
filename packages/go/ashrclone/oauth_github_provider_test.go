package ashrclone

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestGitHubOAuthProviderImplementsExactFirstLoginContract(t *testing.T) {
	const (
		clientID     = "github-client-fixture"
		clientSecret = "github-client-secret-fixture"
		accessToken  = "github-access-token-fixture"
	)
	var revokeCalls atomic.Int32
	server := httptest.NewTLSServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		switch request.URL.Path {
		case "/token":
			if request.Method != http.MethodPost || request.Header.Get("Accept") != "application/json" {
				t.Error("GitHub token exchange request is invalid")
			}
			if err := request.ParseForm(); err != nil {
				t.Error(err)
			}
			if request.Form.Get("client_id") != clientID || request.Form.Get("client_secret") != clientSecret || request.Form.Get("code") != "authorization-code-fixture" || request.Form.Get("code_verifier") != "pkce-verifier-fixture" {
				t.Error("GitHub token exchange lost credentials, code, or PKCE verifier")
			}
			writer.Header().Set("Content-Type", "application/json; charset=utf-8")
			_ = json.NewEncoder(writer).Encode(map[string]string{
				"access_token": accessToken, "token_type": "bearer", "scope": "user:email,read:user",
			})
		case "/user":
			if request.Header.Get("Authorization") != "Bearer "+accessToken {
				t.Error("GitHub identity lookup omitted bearer authorization")
			}
			writer.Header().Set("Content-Type", "application/json")
			_, _ = writer.Write([]byte(`{"id":42,"login":"octocat","name":"Octo Cat"}`))
		case "/user/emails":
			writer.Header().Set("Content-Type", "application/json")
			_, _ = writer.Write([]byte(`[{"email":"secondary@example.test","primary":false,"verified":true},{"email":"primary@example.test","primary":true,"verified":true}]`))
		case "/applications/" + clientID + "/token":
			username, password, ok := request.BasicAuth()
			if request.Method != http.MethodDelete || !ok || username != clientID || password != clientSecret {
				t.Error("GitHub token revocation omitted application authentication")
			}
			revokeCalls.Add(1)
			writer.WriteHeader(http.StatusNoContent)
		default:
			writer.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()
	provider, err := NewGitHubOAuthProvider(GitHubOAuthProviderOptions{
		HTTPClient: server.Client(), AuthorizeURL: server.URL + "/authorize",
		TokenURL: server.URL + "/token", APIURL: server.URL,
		UpstreamTimeout: time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	if provider.Name() != "github" || provider.SchemaVersion() != GitHubOAuthSchemaVersion || strings.Join(provider.ExactScopes(), " ") != "read:user user:email" {
		t.Fatalf("GitHub provider identity/scopes are invalid: name=%q schema=%q scopes=%v", provider.Name(), provider.SchemaVersion(), provider.ExactScopes())
	}
	authorizationURL, err := provider.AuthorizationURL(OAuthAuthorizationRequest{
		ClientID: clientID, CallbackURL: "https://api.example.test/v1/identity/oauth/github/callback",
		State: "state-fixture", CodeChallenge: "challenge-fixture", Nonce: "nonce-not-forwarded",
		Scopes: provider.ExactScopes(),
	})
	if err != nil {
		t.Fatal(err)
	}
	parsed, err := url.Parse(authorizationURL)
	if err != nil || parsed.Query().Get("scope") != "read:user user:email" || parsed.Query().Get("state") != "state-fixture" || parsed.Query().Get("code_challenge_method") != "S256" || parsed.Query().Has("nonce") {
		t.Fatalf("GitHub authorization URL is invalid: %q err=%v", authorizationURL, err)
	}
	credentials := OAuthClientCredentials{ClientID: clientID, ClientSecret: clientSecret}
	tokenSet, err := provider.ExchangeCode(context.Background(), OAuthCodeExchangeRequest{
		Credentials: credentials, CallbackURL: "https://api.example.test/v1/identity/oauth/github/callback",
		Code: "authorization-code-fixture", CodeVerifier: "pkce-verifier-fixture",
	})
	if err != nil || tokenSet.AccessToken != accessToken || strings.Join(tokenSet.Scopes, " ") != "read:user user:email" || tokenSet.IDToken != "" {
		t.Fatalf("GitHub token exchange failed: token=%#v err=%v", tokenSet, err)
	}
	identity, err := provider.ResolveIdentity(context.Background(), OAuthIdentityRequest{TokenSet: tokenSet, Nonce: "unused-github-nonce", ClientID: clientID, Now: time.Now().UTC()})
	if err != nil || identity.Subject != "github:42" || identity.DisplayName != "Octo Cat" || identity.Email != "primary@example.test" || !identity.EmailVerified {
		t.Fatalf("GitHub canonical identity is invalid: identity=%#v err=%v", identity, err)
	}
	if err := provider.RevokeToken(context.Background(), credentials, accessToken); err != nil || revokeCalls.Load() != 1 {
		t.Fatalf("GitHub token revoke failed: calls=%d err=%v", revokeCalls.Load(), err)
	}
}

func TestGitHubOAuthProviderRefusesRedirectAndRedactsUpstreamBody(t *testing.T) {
	const secret = "github-upstream-secret-must-not-leak"
	var redirected atomic.Int32
	server := httptest.NewTLSServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		switch request.URL.Path {
		case "/redirect":
			http.Redirect(writer, request, "/capture", http.StatusTemporaryRedirect)
		case "/capture":
			redirected.Add(1)
			writer.WriteHeader(http.StatusOK)
			_, _ = writer.Write([]byte(`{"access_token":"` + secret + `","token_type":"bearer","scope":"read:user,user:email"}`))
		case "/failure":
			writer.WriteHeader(http.StatusBadGateway)
			_, _ = writer.Write([]byte(secret))
		default:
			writer.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()
	for _, path := range []string{"/redirect", "/failure"} {
		provider, err := NewGitHubOAuthProvider(GitHubOAuthProviderOptions{
			HTTPClient: server.Client(), AuthorizeURL: server.URL + "/authorize",
			TokenURL: server.URL + path, APIURL: server.URL, UpstreamTimeout: time.Second,
		})
		if err != nil {
			t.Fatal(err)
		}
		_, err = provider.ExchangeCode(context.Background(), OAuthCodeExchangeRequest{
			Credentials: OAuthClientCredentials{ClientID: "client", ClientSecret: secret},
			CallbackURL: "https://api.example.test/v1/identity/oauth/github/callback",
			Code:        "code", CodeVerifier: "verifier",
		})
		if err == nil || strings.Contains(err.Error(), secret) {
			t.Fatalf("GitHub unsafe upstream result was accepted or leaked: %v", err)
		}
	}
	if redirected.Load() != 0 {
		t.Fatal("GitHub credential-bearing request followed a redirect")
	}
}

func TestGitHubOAuthProviderRequiresStrictConfigurationAndInputs(t *testing.T) {
	for _, options := range []GitHubOAuthProviderOptions{
		{AuthorizeURL: "http://github.example.test/authorize", TokenURL: "https://github.example.test/token", APIURL: "https://api.example.test", UpstreamTimeout: time.Second},
		{AuthorizeURL: "https://github.example.test/authorize", TokenURL: "https://github.example.test/token?query=forbidden", APIURL: "https://api.example.test", UpstreamTimeout: time.Second},
		{AuthorizeURL: "https://github.example.test/authorize", TokenURL: "https://github.example.test/token", APIURL: "https://api.example.test/path", UpstreamTimeout: time.Second},
		{AuthorizeURL: "https://github.example.test/authorize", TokenURL: "https://github.example.test/token", APIURL: "https://api.example.test", UpstreamTimeout: 0},
	} {
		if _, err := NewGitHubOAuthProvider(options); err == nil {
			t.Fatal("invalid GitHub provider configuration was accepted")
		}
	}
	provider, err := NewGitHubOAuthProvider(GitHubOAuthProviderOptions{UpstreamTimeout: time.Second})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := provider.AuthorizationURL(OAuthAuthorizationRequest{ClientID: "client", CallbackURL: "https://api.example.test/v1/identity/oauth/github/callback", State: "state", CodeChallenge: "challenge", Scopes: []string{"read:user"}}); err == nil {
		t.Fatal("GitHub provider accepted a non-exact scope set")
	}
}
