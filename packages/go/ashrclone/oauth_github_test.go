package ashrclone

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strconv"
	"strings"
	"testing"
	"time"
)

type testGitHubOAuthCredentials struct{}

func (testGitHubOAuthCredentials) GitHubOAuthCredentials(context.Context) (GitHubOAuthCredentials, error) {
	return GitHubOAuthCredentials{ClientID: "client-id", ClientSecret: "client-secret"}, nil
}

type testGitHubOAuthSessionResolver struct {
	session GitHubOAuthSession
}

func (resolver testGitHubOAuthSessionResolver) ResolveGitHubOAuthSession(context.Context, *http.Request) (GitHubOAuthSession, error) {
	return resolver.session, nil
}

type testGitHubOAuthRoundTripper func(*http.Request) (*http.Response, error)

func (transport testGitHubOAuthRoundTripper) RoundTrip(request *http.Request) (*http.Response, error) {
	return transport(request)
}

func TestGitHubOAuthHTTPVerticalSliceAndReplayDenial(t *testing.T) {
	now := time.Date(2026, 7, 10, 1, 2, 3, 0, time.UTC)
	store := NewMemoryGitHubOAuthStore()
	var exchangedVerifier string
	client := &http.Client{Transport: testGitHubOAuthRoundTripper(func(request *http.Request) (*http.Response, error) {
		body := `{"id":42,"login":"octocat","email":null}`
		if request.URL.Path == "/token" {
			if err := request.ParseForm(); err != nil {
				t.Fatal(err)
			}
			exchangedVerifier = request.Form.Get("code_verifier")
			body = `{"access_token":"github-access-token","token_type":"bearer","scope":"read:user"}`
		}
		if request.Method == http.MethodDelete {
			return &http.Response{StatusCode: http.StatusNoContent, Header: make(http.Header), Body: io.NopCloser(strings.NewReader("")), Request: request}, nil
		}
		return &http.Response{StatusCode: http.StatusOK, Header: make(http.Header), Body: io.NopCloser(strings.NewReader(body)), Request: request}, nil
	})}
	oauth, err := NewGitHubOAuthService(GitHubOAuthOptions{
		SessionResolver: testGitHubOAuthSessionResolver{session: GitHubOAuthSession{TenantID: "tenant", UserID: "user", SessionID: "session"}},
		Credentials:     testGitHubOAuthCredentials{}, Transactions: store, Secrets: store, Connections: store, HTTPClient: client,
		AuthorizeURL: "http://github.test/authorize", TokenURL: "http://github.test/token", APIURL: "http://github.test",
		CallbackURL: "http://localhost:8787/oauth/github/callback", TransactionTTL: time.Minute, Now: func() time.Time { return now },
	})
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{GitHubOAuth: oauth}))
	defer server.Close()

	startRequest, _ := http.NewRequest(http.MethodPost, server.URL+"/v1/projects/project/oauth/github/start", strings.NewReader(`{"tenant_id":"tenant","account_id":"account"}`))
	startRequest.Header.Set("Content-Type", "application/json")
	startResponse, err := http.DefaultClient.Do(startRequest)
	if err != nil {
		t.Fatal(err)
	}
	var start GitHubOAuthStartResult
	if err := json.NewDecoder(startResponse.Body).Decode(&start); err != nil {
		t.Fatal(err)
	}
	_ = startResponse.Body.Close()
	authorizeURL, err := url.Parse(start.AuthorizationURL)
	if err != nil {
		t.Fatal(err)
	}
	if authorizeURL.Query().Get("code_challenge_method") != "S256" || authorizeURL.Query().Get("state") == "" {
		t.Fatalf("missing state or PKCE S256: %s", start.AuthorizationURL)
	}
	state := authorizeURL.Query().Get("state")
	callbackResponse, err := http.Get(server.URL + "/oauth/github/callback?code=code&state=" + url.QueryEscape(state))
	if err != nil {
		t.Fatal(err)
	}
	callbackBody := readTestResponseBody(t, callbackResponse)
	if callbackResponse.StatusCode != http.StatusOK || exchangedVerifier == "" {
		t.Fatalf("callback failed: status=%d body=%s", callbackResponse.StatusCode, callbackBody)
	}
	for _, secret := range []string{"github-access-token", "client-secret", exchangedVerifier, "github_oauth_ref_"} {
		if strings.Contains(callbackBody, secret) {
			t.Fatalf("secret leaked in callback response: %q", secret)
		}
	}
	replayResponse, err := http.Get(server.URL + "/oauth/github/callback?code=code&state=" + url.QueryEscape(state))
	if err != nil {
		t.Fatal(err)
	}
	if replayResponse.StatusCode != http.StatusBadRequest {
		t.Fatalf("replay status=%d body=%s", replayResponse.StatusCode, readTestResponseBody(t, replayResponse))
	}
	_ = replayResponse.Body.Close()
}

func TestGitHubOAuthEnvConfigurationFailsClosed(t *testing.T) {
	env := map[string]string{
		"ASHR_GITHUB_OAUTH_ENABLED": "true", "ASHR_GITHUB_OAUTH_DEV_SESSION_ENABLED": "true",
		"ASHR_GITHUB_OAUTH_CALLBACK_URL":  "http://localhost:8787/oauth/github/callback",
		"ASHR_GITHUB_OAUTH_DEV_TENANT_ID": "tenant", "ASHR_GITHUB_OAUTH_DEV_USER_ID": "user", "ASHR_GITHUB_OAUTH_DEV_SESSION_ID": "session",
		"ASHR_GITHUB_OAUTH_CLIENT_ID": "same", "ASHR_GITHUB_OAUTH_CLIENT_SECRET": "same",
	}
	lookup := func(key string) (string, bool) { value, ok := env[key]; return value, ok }
	_, err := NewGitHubOAuthServiceFromEnv(GitHubOAuthEnvRuntimeOptions{LookupEnv: lookup})
	if err == nil || strings.Contains(err.Error(), "same") {
		t.Fatalf("expected redacted unequal-credential failure, got %v", err)
	}
	delete(env, "ASHR_GITHUB_OAUTH_DEV_SESSION_ENABLED")
	if _, err := NewGitHubOAuthServiceFromEnv(GitHubOAuthEnvRuntimeOptions{LookupEnv: lookup}); err == nil {
		t.Fatal("expected explicit dev session enablement requirement")
	}
}

func TestGitHubOAuthTokenExchangeRequiresExactCommaSeparatedScopeSet(t *testing.T) {
	tests := []struct {
		name          string
		requested     []string
		granted       string
		wantErrorCode string
	}{
		{name: "ordered", requested: []string{"read:user", "user:email"}, granted: "read:user,user:email"},
		{name: "reordered", requested: []string{"read:user", "user:email"}, granted: " user:email , read:user "},
		{name: "duplicate normalized", requested: []string{"read:user", "user:email"}, granted: "read:user,user:email,read:user"},
		{name: "unexpected scope", requested: []string{"read:user"}, granted: "read:user,repo", wantErrorCode: "github_scope_escalation"},
		{name: "missing scope", requested: []string{"read:user", "user:email"}, granted: "read:user", wantErrorCode: "github_scope_mismatch"},
		{name: "empty scope", requested: []string{"read:user"}, granted: "", wantErrorCode: "github_scope_mismatch"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			client := &http.Client{Transport: testGitHubOAuthRoundTripper(func(request *http.Request) (*http.Response, error) {
				body := `{"access_token":"github-access-token","token_type":"bearer","scope":` + strconv.Quote(test.granted) + `}`
				return &http.Response{StatusCode: http.StatusOK, Header: make(http.Header), Body: io.NopCloser(strings.NewReader(body)), Request: request}, nil
			})}
			service, err := NewGitHubOAuthService(GitHubOAuthOptions{
				SessionResolver: testGitHubOAuthSessionResolver{session: GitHubOAuthSession{TenantID: "tenant", UserID: "user", SessionID: "session"}},
				Credentials:     testGitHubOAuthCredentials{}, Transactions: NewMemoryGitHubOAuthStore(),
				Secrets: NewMemoryGitHubOAuthStore(), Connections: NewMemoryGitHubOAuthStore(), HTTPClient: client,
				AuthorizeURL: "http://github.test/authorize", TokenURL: "http://github.test/token", APIURL: "http://github.test",
				CallbackURL: "http://localhost:8787/oauth/github/callback", Scopes: test.requested,
			})
			if err != nil {
				t.Fatal(err)
			}
			token, exchangeErr := service.exchangeCode(context.Background(), GitHubOAuthCredentials{ClientID: "client-id", ClientSecret: "client-secret"}, "code", "verifier")
			if test.wantErrorCode == "" {
				if exchangeErr != nil || token == "" {
					t.Fatalf("expected exchange success, token_present=%t err=%v", token != "", exchangeErr)
				}
				return
			}
			var oauthErr GitHubOAuthError
			if exchangeErr == nil || !errors.As(exchangeErr, &oauthErr) || oauthErr.Code != test.wantErrorCode {
				t.Fatalf("expected %s, got %#v", test.wantErrorCode, exchangeErr)
			}
		})
	}
}

func TestLocalhostDevSessionRejectsSpoofedHost(t *testing.T) {
	resolver := LocalhostDevGitHubOAuthSessionResolver{Enabled: true, TenantID: "tenant", UserID: "user", SessionID: "session"}
	request := httptest.NewRequest(http.MethodPost, "http://localhost:8787/v1/projects/project/oauth/github/start", nil)
	request.RemoteAddr = "203.0.113.7:4242"
	if _, err := resolver.ResolveGitHubOAuthSession(context.Background(), request); err == nil {
		t.Fatal("expected remote request with spoofed localhost Host to be rejected")
	}
	request.RemoteAddr = "127.0.0.1:4242"
	request.Header.Set("X-Forwarded-For", "203.0.113.7")
	if _, err := resolver.ResolveGitHubOAuthSession(context.Background(), request); err == nil {
		t.Fatal("expected forwarded request to be rejected")
	}
}

func TestGitHubOAuthDisconnectRevokesBeforeDeletingLocalToken(t *testing.T) {
	now := time.Date(2026, 7, 10, 1, 2, 3, 0, time.UTC)
	store := NewMemoryGitHubOAuthStore()
	binding := GitHubOAuthSecretBinding{TenantID: "tenant", ProjectID: "project", SessionID: "session", UserID: "user", AccountID: "account"}
	ref, err := store.PutGitHubOAuthToken(context.Background(), binding, "github-access-token")
	if err != nil {
		t.Fatal(err)
	}
	_, err = store.UpsertGitHubOAuthConnection(context.Background(), GitHubOAuthConnection{
		SchemaVersion: GitHubOAuthSchemaVersion, TenantID: binding.TenantID, ProjectID: binding.ProjectID,
		SessionID: binding.SessionID, UserID: binding.UserID, AccountID: binding.AccountID, TokenRef: ref, ConnectedAt: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	revokeStatus := http.StatusBadGateway
	client := &http.Client{Transport: testGitHubOAuthRoundTripper(func(request *http.Request) (*http.Response, error) {
		if request.Method != http.MethodDelete || request.URL.Path != "/applications/client-id/token" {
			t.Fatalf("unexpected revoke request: %s %s", request.Method, request.URL.Path)
		}
		if username, password, ok := request.BasicAuth(); !ok || username != "client-id" || password != "client-secret" {
			t.Fatal("revoke request did not use client credentials")
		}
		return &http.Response{StatusCode: revokeStatus, Header: make(http.Header), Body: io.NopCloser(strings.NewReader("")), Request: request}, nil
	})}
	service, err := NewGitHubOAuthService(GitHubOAuthOptions{
		SessionResolver: testGitHubOAuthSessionResolver{session: GitHubOAuthSession{TenantID: "tenant", UserID: "user", SessionID: "session"}},
		Credentials:     testGitHubOAuthCredentials{}, Transactions: store, Secrets: store, Connections: store, HTTPClient: client,
		AuthorizeURL: "http://github.test/authorize", TokenURL: "http://github.test/token", APIURL: "http://github.test",
		CallbackURL: "http://localhost:8787/oauth/github/callback", Now: func() time.Time { return now },
	})
	if err != nil {
		t.Fatal(err)
	}
	localRequest := httptest.NewRequest(http.MethodPost, "http://localhost:8787/v1/projects/project/oauth/github/disconnect", nil)
	localRequest.RemoteAddr = "127.0.0.1:4242"
	if _, err := service.Disconnect(context.Background(), localRequest, "tenant", "project", "account"); err == nil {
		t.Fatal("expected provider revoke failure")
	}
	if _, err := store.GetGitHubOAuthToken(context.Background(), ref); err != nil {
		t.Fatal("provider revoke failure must retain local token reference")
	}
	if _, err := store.GetGitHubOAuthConnection(context.Background(), binding); err != nil {
		t.Fatal("provider revoke failure must retain active connection")
	}
	revokeStatus = http.StatusNoContent
	result, err := service.Disconnect(context.Background(), localRequest, "tenant", "project", "account")
	if err != nil || !result.Disconnected {
		t.Fatalf("disconnect failed: result=%+v err=%v", result, err)
	}
	if _, err := store.GetGitHubOAuthToken(context.Background(), ref); err == nil {
		t.Fatal("successful revoke must delete local token")
	}
}

func TestGitHubOAuthRoutesInManifest(t *testing.T) {
	routes := strings.Join(GoRouteManifestRoutes(GoRouteManifestEntries()), "\n")
	for _, route := range []string{
		"GET /oauth/github/callback",
		"GET /v1/projects/{project_id}/oauth/github/start",
		"POST /v1/projects/{project_id}/oauth/github/disconnect",
	} {
		if !strings.Contains(routes, route) {
			t.Fatalf("missing route %s", route)
		}
	}
	if strings.Contains(routes, "GET /v1/oauth/github/callback") {
		t.Fatal("versioned GitHub OAuth callback alias must not be public")
	}
}

func TestGitHubOAuthPublicConnectionMinimizesIdentityDisclosure(t *testing.T) {
	connection := GitHubOAuthConnection{
		SchemaVersion: GitHubOAuthSchemaVersion,
		TenantID:      "tenant", ProjectID: "project", SessionID: "session", UserID: "user",
		AccountID: "account", GitHubUserID: 42, GitHubLogin: "octocat",
		ProviderSubjectHash: githubProviderSubjectSHA256(42),
		Email:               "verified@example.invalid", EmailPresent: true, TokenRef: "github_oauth_ref_private",
		ConnectedAt: time.Date(2026, 7, 10, 1, 2, 3, 0, time.UTC),
	}
	payload, err := json.Marshal(connection)
	if err != nil {
		t.Fatal(err)
	}
	text := string(payload)
	for _, forbidden := range []string{"tenant", "project", "session", "user", "verified@example.invalid", "github_oauth_ref_private", `"github_user_id"`} {
		if strings.Contains(text, forbidden) {
			t.Fatalf("public connection leaked %q: %s", forbidden, text)
		}
	}
	for _, required := range []string{`"account_id":"account"`, `"github_login":"octocat"`, `"email_present":true`, `"provider_subject_sha256"`} {
		if !strings.Contains(text, required) {
			t.Fatalf("public connection omitted %q: %s", required, text)
		}
	}
}

func readTestResponseBody(t *testing.T, response *http.Response) string {
	t.Helper()
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatal(err)
	}
	return string(body)
}
