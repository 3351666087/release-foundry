package releasefoundry

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"
)

type providerHTTPTestAdapter struct {
	name         string
	revokedToken string
}

func (provider *providerHTTPTestAdapter) Name() string { return provider.name }

func (provider *providerHTTPTestAdapter) SchemaVersion() string {
	return "releasefoundry." + provider.name + "_oauth.v1"
}

func (provider *providerHTTPTestAdapter) ExactScopes() []string {
	return []string{"email", "openid", "profile"}
}

func (provider *providerHTTPTestAdapter) AuthorizationURL(request OAuthAuthorizationRequest) (string, error) {
	values := url.Values{
		"client_id":      {request.ClientID},
		"redirect_uri":   {request.CallbackURL},
		"state":          {request.State},
		"nonce":          {request.Nonce},
		"code_challenge": {request.CodeChallenge},
		"scope":          {strings.Join(request.Scopes, " ")},
	}
	return "https://accounts.google.test/authorize?" + values.Encode(), nil
}

func (provider *providerHTTPTestAdapter) ExchangeCode(context.Context, OAuthCodeExchangeRequest) (OAuthTokenSet, error) {
	return OAuthTokenSet{
		AccessToken: "provider-access-token",
		TokenType:   "Bearer",
		Scopes:      provider.ExactScopes(),
		IDToken:     "provider-id-token",
	}, nil
}

func (provider *providerHTTPTestAdapter) ResolveIdentity(context.Context, OAuthIdentityRequest) (OAuthProviderIdentity, error) {
	return OAuthProviderIdentity{
		Subject:       "provider-subject",
		DisplayName:   "OAuth Test User",
		Email:         "private@example.invalid",
		EmailVerified: true,
	}, nil
}

func (provider *providerHTTPTestAdapter) RevokeToken(_ context.Context, _ OAuthClientCredentials, token string) error {
	provider.revokedToken = token
	return nil
}

func TestProviderNeutralOAuthHTTPGoogleLifecycleAndPublicRedaction(t *testing.T) {
	adapter := &providerHTTPTestAdapter{name: "google"}
	service := newProviderHTTPTestService(t, adapter)
	server := httptest.NewServer(NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		OAuthProviders: map[string]*OAuthService{" GOOGLE ": service},
	}))
	defer server.Close()

	startRequest, err := http.NewRequest(
		http.MethodPost,
		server.URL+"/v1/projects/project/oauth/google/start",
		strings.NewReader(`{"tenant_id":"tenant","account_id":"account"}`),
	)
	if err != nil {
		t.Fatal(err)
	}
	startRequest.Header.Set("Content-Type", "application/json")
	startResponse, err := http.DefaultClient.Do(startRequest)
	if err != nil {
		t.Fatal(err)
	}
	var start OAuthStartResult
	decodeProviderHTTPTestResponse(t, startResponse, http.StatusOK, &start)
	if start.Provider != "google" || start.AuthorizationURL == "" {
		t.Fatalf("unexpected Google start response: %+v", start)
	}
	authorizeURL, err := url.Parse(start.AuthorizationURL)
	if err != nil {
		t.Fatal(err)
	}
	state := authorizeURL.Query().Get("state")
	if state == "" || authorizeURL.Query().Get("nonce") == "" || authorizeURL.Query().Get("code_challenge") == "" {
		t.Fatalf("Google start omitted state, nonce, or PKCE challenge: %s", start.AuthorizationURL)
	}

	callbackResponse, err := http.Get(server.URL + "/oauth/google/callback?code=code&state=" + url.QueryEscape(state))
	if err != nil {
		t.Fatal(err)
	}
	callbackBody := decodeProviderHTTPTestJSON(t, callbackResponse, http.StatusOK)
	assertProviderHTTPPublicRedaction(t, callbackBody)
	if callbackBody["provider"] != "google" {
		t.Fatalf("callback provider=%v", callbackBody["provider"])
	}

	connectionResponse, err := http.Get(server.URL + "/v1/projects/project/oauth/google/connection?tenant_id=tenant&account_id=account")
	if err != nil {
		t.Fatal(err)
	}
	connectionBody := decodeProviderHTTPTestJSON(t, connectionResponse, http.StatusOK)
	assertProviderHTTPPublicRedaction(t, connectionBody)
	if connectionBody["account_id"] != "account" || connectionBody["email_present"] != true {
		t.Fatalf("unexpected public connection: %#v", connectionBody)
	}

	disconnectRequest, err := http.NewRequest(
		http.MethodDelete,
		server.URL+"/v1/projects/project/oauth/google/disconnect?tenant_id=tenant&account_id=account",
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	disconnectResponse, err := http.DefaultClient.Do(disconnectRequest)
	if err != nil {
		t.Fatal(err)
	}
	disconnectBody := decodeProviderHTTPTestJSON(t, disconnectResponse, http.StatusOK)
	assertProviderHTTPPublicRedaction(t, disconnectBody)
	if disconnectBody["provider"] != "google" || disconnectBody["disconnected"] != true {
		t.Fatalf("unexpected disconnect response: %#v", disconnectBody)
	}
	if adapter.revokedToken != "provider-access-token" {
		t.Fatalf("provider revoke token=%q", adapter.revokedToken)
	}

	missingResponse, err := http.Get(server.URL + "/v1/projects/project/oauth/google/connection?tenant_id=tenant&account_id=account")
	if err != nil {
		t.Fatal(err)
	}
	decodeProviderHTTPTestResponse(t, missingResponse, http.StatusNotFound, &map[string]any{})
}

func TestProviderNeutralOAuthHTTPUnknownAndInvalidProvidersAreNotRoutable(t *testing.T) {
	google := newProviderHTTPTestService(t, &providerHTTPTestAdapter{name: "google"})
	server := httptest.NewServer(NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		OAuthProviders: map[string]*OAuthService{
			"":          google,
			"../google": google,
			"github":    google,
			"nil":       nil,
		},
	}))
	defer server.Close()

	for _, path := range []string{
		"/oauth/unknown/callback",
		"/oauth/google/callback",
		"/v1/projects/project/oauth/unknown/start",
		"/v1/projects/project/oauth/google/start",
		"/v1/projects/project/oauth/github/start",
	} {
		response, err := http.Get(server.URL + path)
		if err != nil {
			t.Fatal(err)
		}
		body := decodeProviderHTTPTestJSON(t, response, http.StatusNotFound)
		if code := providerHTTPTestErrorCode(body); code != "not_found" {
			t.Fatalf("%s code=%v body=%#v", path, code, body)
		}
	}
}

func TestProviderNeutralOAuthHTTPRejectsUnsupportedMethods(t *testing.T) {
	service := newProviderHTTPTestService(t, &providerHTTPTestAdapter{name: "google"})
	server := httptest.NewServer(NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		OAuthProviders: map[string]*OAuthService{"google": service},
	}))
	defer server.Close()

	tests := []struct {
		method string
		path   string
	}{
		{method: http.MethodPut, path: "/v1/projects/project/oauth/google/start"},
		{method: http.MethodPost, path: "/v1/projects/project/oauth/google/connection"},
		{method: http.MethodPatch, path: "/v1/projects/project/oauth/google/disconnect"},
		{method: http.MethodPost, path: "/oauth/google/callback"},
	}
	for _, test := range tests {
		t.Run(test.method+" "+test.path, func(t *testing.T) {
			request, err := http.NewRequest(test.method, server.URL+test.path, nil)
			if err != nil {
				t.Fatal(err)
			}
			response, err := http.DefaultClient.Do(request)
			if err != nil {
				t.Fatal(err)
			}
			body := decodeProviderHTTPTestJSON(t, response, http.StatusMethodNotAllowed)
			if code := providerHTTPTestErrorCode(body); code != "method_not_allowed" {
				t.Fatalf("code=%v body=%#v", code, body)
			}
		})
	}
}

func TestProviderNeutralOAuthHTTPRouteManifestIncludesGoogleAndGitHubCompatibility(t *testing.T) {
	entries := GoRouteManifestEntries()
	byRoute := make(map[string]RouteManifestEntry, len(entries))
	for _, entry := range entries {
		byRoute[entry.Route] = entry
	}
	for _, route := range []string{
		"GET /v1/projects/{project_id}/oauth/google/start",
		"POST /v1/projects/{project_id}/oauth/google/start",
		"GET /oauth/google/callback",
		"GET /v1/projects/{project_id}/oauth/google/connection",
		"POST /v1/projects/{project_id}/oauth/google/disconnect",
		"DELETE /v1/projects/{project_id}/oauth/google/disconnect",
		"GET /v1/projects/{project_id}/oauth/github/start",
		"POST /v1/projects/{project_id}/oauth/github/start",
		"GET /oauth/github/callback",
		"GET /v1/projects/{project_id}/oauth/github/connection",
		"POST /v1/projects/{project_id}/oauth/github/disconnect",
		"DELETE /v1/projects/{project_id}/oauth/github/disconnect",
	} {
		entry, ok := byRoute[route]
		if !ok {
			t.Fatalf("route manifest omitted %s", route)
		}
		if !entry.PublicSafe || entry.Category != "oauth" {
			t.Fatalf("route manifest metadata for %s: %+v", route, entry)
		}
	}
	if byRoute["GET /oauth/google/callback"].AuthRequired || byRoute["GET /oauth/github/callback"].AuthRequired {
		t.Fatal("OAuth callbacks must remain public")
	}
	if !byRoute["GET /v1/projects/{project_id}/oauth/google/connection"].AuthRequired ||
		!byRoute["GET /v1/projects/{project_id}/oauth/github/connection"].AuthRequired {
		t.Fatal("project OAuth connection routes must remain scoped")
	}
}

func TestProviderNeutralOAuthHTTPKeepsLegacyGitHubRoutingPrecedence(t *testing.T) {
	genericGitHub := newProviderHTTPTestService(t, &providerHTTPTestAdapter{name: "github"})
	server := httptest.NewServer(NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		OAuthProviders: map[string]*OAuthService{"github": genericGitHub},
		GitHubOAuth:    newProviderHTTPTestGitHubService(t),
	}))
	defer server.Close()

	startRequest, err := http.NewRequest(
		http.MethodPost,
		server.URL+"/v1/projects/project/oauth/github/start",
		strings.NewReader(`{"tenant_id":"tenant","account_id":"account"}`),
	)
	if err != nil {
		t.Fatal(err)
	}
	startRequest.Header.Set("Content-Type", "application/json")
	startResponse, err := http.DefaultClient.Do(startRequest)
	if err != nil {
		t.Fatal(err)
	}
	var start GitHubOAuthStartResult
	decodeProviderHTTPTestResponse(t, startResponse, http.StatusOK, &start)
	if !strings.HasPrefix(start.AuthorizationURL, "https://github.test/authorize?") {
		t.Fatalf("legacy GitHub route lost precedence: %s", start.AuthorizationURL)
	}
}

func newProviderHTTPTestService(t *testing.T, adapter OAuthProviderAdapter) *OAuthService {
	t.Helper()
	store := NewMemoryOAuthStore()
	identity, err := NewUnifiedIdentityService(UnifiedIdentityServiceOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := identity.EnsureAccount("account", "user"); err != nil {
		t.Fatal(err)
	}
	if _, err := identity.LinkCredential("account", LinkIdentityCredentialRequest{
		Credential: IdentityCredentialInput{
			Kind: IdentityCredentialEmail, Provider: IdentityProviderLocal,
			Identifier: "backup@example.invalid", Verified: true,
		},
		ActorID: "user",
	}); err != nil {
		t.Fatal(err)
	}
	service, err := NewOAuthService(OAuthServiceOptions{
		Provider: adapter,
		SessionResolver: oauthTestSessionResolver{session: OAuthSession{
			TenantID: "tenant", UserID: "user", SessionID: "session", AccountID: "account",
		}},
		Credentials:    oauthTestCredentials{},
		Transactions:   store,
		Secrets:        store,
		Connections:    store,
		IdentityBridge: UnifiedIdentityOAuthBridge{Identity: identity},
		CallbackURL:    "http://localhost:8787/oauth/" + adapter.Name() + "/callback",
		TransactionTTL: time.Minute,
		Now: func() time.Time {
			return time.Date(2026, 7, 10, 8, 9, 10, 0, time.UTC)
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	return service
}

func newProviderHTTPTestGitHubService(t *testing.T) *GitHubOAuthService {
	t.Helper()
	store := NewMemoryGitHubOAuthStore()
	service, err := NewGitHubOAuthService(GitHubOAuthOptions{
		SessionResolver: testGitHubOAuthSessionResolver{session: GitHubOAuthSession{
			TenantID: "tenant", UserID: "user", SessionID: "session", AccountID: "account",
		}},
		Credentials:  testGitHubOAuthCredentials{},
		Transactions: store,
		Secrets:      store,
		Connections:  store,
		AuthorizeURL: "https://github.test/authorize",
		TokenURL:     "https://github.test/token",
		APIURL:       "https://github.test/api",
		CallbackURL:  "http://localhost:8787/oauth/github/callback",
	})
	if err != nil {
		t.Fatal(err)
	}
	return service
}

func decodeProviderHTTPTestResponse(t *testing.T, response *http.Response, wantStatus int, target any) {
	t.Helper()
	defer response.Body.Close()
	if response.StatusCode != wantStatus {
		var body map[string]any
		_ = json.NewDecoder(response.Body).Decode(&body)
		t.Fatalf("status=%d want=%d body=%#v", response.StatusCode, wantStatus, body)
	}
	if err := json.NewDecoder(response.Body).Decode(target); err != nil {
		t.Fatal(err)
	}
}

func decodeProviderHTTPTestJSON(t *testing.T, response *http.Response, wantStatus int) map[string]any {
	t.Helper()
	var body map[string]any
	decodeProviderHTTPTestResponse(t, response, wantStatus, &body)
	return body
}

func assertProviderHTTPPublicRedaction(t *testing.T, body map[string]any) {
	t.Helper()
	payload, err := json.Marshal(body)
	if err != nil {
		t.Fatal(err)
	}
	text := string(payload)
	for _, forbidden := range []string{
		"provider-access-token",
		"provider-id-token",
		"client-secret",
		"private@example.invalid",
		"_oauth_ref_",
		`"tenant_id"`,
		`"project_id"`,
		`"session_id"`,
		`"user_id"`,
		`"token_ref"`,
	} {
		if strings.Contains(text, forbidden) {
			t.Fatalf("public OAuth response leaked %q: %s", forbidden, text)
		}
	}
}

func providerHTTPTestErrorCode(body map[string]any) string {
	errorBody, ok := body["error"].(map[string]any)
	if !ok {
		return ""
	}
	code, _ := errorBody["code"].(string)
	return code
}
