package releasefoundry

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync"
	"testing"
	"time"
)

type oauthFirstLoginHTTPAdapter struct {
	name       string
	lastAuth   OAuthAuthorizationRequest
	lastCode   OAuthCodeExchangeRequest
	lastID     OAuthIdentityRequest
	revokeCall int
}

func (adapter *oauthFirstLoginHTTPAdapter) Name() string { return adapter.name }

func (adapter *oauthFirstLoginHTTPAdapter) SchemaVersion() string {
	return "releasefoundry." + adapter.name + "_oauth.v1"
}

func (adapter *oauthFirstLoginHTTPAdapter) ExactScopes() []string {
	return []string{"identity"}
}

func (adapter *oauthFirstLoginHTTPAdapter) AuthorizationURL(
	request OAuthAuthorizationRequest,
) (string, error) {
	adapter.lastAuth = request
	endpoint, _ := url.Parse("https://" + adapter.name + ".example.invalid/authorize")
	query := endpoint.Query()
	query.Set("client_id", request.ClientID)
	query.Set("redirect_uri", request.CallbackURL)
	query.Set("state", request.State)
	query.Set("nonce", request.Nonce)
	query.Set("code_challenge", request.CodeChallenge)
	endpoint.RawQuery = query.Encode()
	return endpoint.String(), nil
}

func (adapter *oauthFirstLoginHTTPAdapter) ExchangeCode(
	_ context.Context,
	request OAuthCodeExchangeRequest,
) (OAuthTokenSet, error) {
	adapter.lastCode = request
	if request.Code != "provider-code" {
		return OAuthTokenSet{}, errors.New("unexpected provider code")
	}
	return OAuthTokenSet{
		AccessToken: "provider-access-token",
		TokenType:   "Bearer",
		Scopes:      []string{"identity"},
	}, nil
}

func (adapter *oauthFirstLoginHTTPAdapter) ResolveIdentity(
	_ context.Context,
	request OAuthIdentityRequest,
) (OAuthProviderIdentity, error) {
	adapter.lastID = request
	return OAuthProviderIdentity{
		Subject:       "provider-subject",
		DisplayName:   "First Login User",
		Email:         "first-login@example.invalid",
		EmailVerified: true,
	}, nil
}

func (adapter *oauthFirstLoginHTTPAdapter) RevokeToken(
	context.Context,
	OAuthClientCredentials,
	string,
) error {
	adapter.revokeCall++
	return nil
}

type oauthFirstLoginHTTPTransactions struct {
	mu           sync.Mutex
	transactions map[string]OAuthFirstLoginTransaction
	creates      int
	consumes     int
}

func (store *oauthFirstLoginHTTPTransactions) CreateOAuthFirstLoginTransaction(
	_ context.Context,
	transaction OAuthFirstLoginTransaction,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.transactions == nil {
		store.transactions = map[string]OAuthFirstLoginTransaction{}
	}
	key := transaction.Provider + "\x00" + transaction.StateHash
	if _, exists := store.transactions[key]; exists {
		return errors.New("state collision")
	}
	store.transactions[key] = transaction
	store.creates++
	return nil
}

func (store *oauthFirstLoginHTTPTransactions) ConsumeOAuthFirstLoginTransaction(
	_ context.Context,
	provider string,
	stateHash string,
	now time.Time,
) (OAuthFirstLoginTransaction, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	key := provider + "\x00" + stateHash
	transaction, exists := store.transactions[key]
	if !exists {
		return OAuthFirstLoginTransaction{}, ErrOAuthTransactionNotFound
	}
	delete(store.transactions, key)
	store.consumes++
	if !now.Before(transaction.ExpiresAt) {
		return OAuthFirstLoginTransaction{}, ErrOAuthTransactionExpired
	}
	return transaction, nil
}

type oauthFirstLoginHTTPSecrets struct {
	lastBinding OAuthSecretBinding
	putCalls    int
	deleteCalls int
}

func (store *oauthFirstLoginHTTPSecrets) PutOAuthToken(
	_ context.Context,
	binding OAuthSecretBinding,
	token string,
) (string, error) {
	if token != "provider-access-token" {
		return "", errors.New("unexpected token")
	}
	store.lastBinding = binding
	store.putCalls++
	return "vault_ref_oauth_first_login", nil
}

func (*oauthFirstLoginHTTPSecrets) GetOAuthToken(context.Context, string) (string, error) {
	return "", errors.New("not used")
}

func (store *oauthFirstLoginHTTPSecrets) DeleteOAuthToken(
	context.Context,
	string,
) error {
	store.deleteCalls++
	return nil
}

type oauthFirstLoginHTTPCoordinator struct {
	mu      sync.Mutex
	command OAuthFirstLoginCompletionCommand
	calls   int
	now     time.Time
}

func (coordinator *oauthFirstLoginHTTPCoordinator) CompleteOAuthFirstLogin(
	_ context.Context,
	command OAuthFirstLoginCompletionCommand,
) (OAuthFirstLoginCompletionResult, IdentitySessionIssuanceReceipt, error) {
	coordinator.mu.Lock()
	defer coordinator.mu.Unlock()
	coordinator.command = command
	coordinator.calls++
	return OAuthFirstLoginCompletionResult{
			SchemaVersion: OAuthFirstLoginSchemaVersion,
			Provider:      command.Provider,
			AccountID:     "principal-1",
			CredentialID:  "credential-1",
			SessionID:     "session-1",
			Created:       true,
		},
		newIdentitySessionIssuanceReceiptWithRefresh(
			"session-1",
			"session-key-v1",
			"refresh-key-v1",
			coordinator.now.Add(time.Hour),
			coordinator.now.Add(24*time.Hour),
			"browser-access-bearer",
			"browser-refresh-bearer",
		),
		nil
}

func newOAuthFirstLoginHTTPFixture(
	t *testing.T,
) (
	http.Handler,
	*oauthFirstLoginHTTPAdapter,
	*oauthFirstLoginHTTPTransactions,
	*oauthFirstLoginHTTPSecrets,
	*oauthFirstLoginHTTPCoordinator,
	*IdentitySessionCookieTransport,
) {
	t.Helper()
	now := time.Date(2026, 7, 23, 8, 9, 10, 0, time.UTC)
	adapter := &oauthFirstLoginHTTPAdapter{name: "google"}
	transactions := &oauthFirstLoginHTTPTransactions{}
	secrets := &oauthFirstLoginHTTPSecrets{}
	coordinator := &oauthFirstLoginHTTPCoordinator{now: now}
	service, err := NewOAuthFirstLoginService(OAuthFirstLoginServiceOptions{
		Provider:       adapter,
		Credentials:    oauthTestCredentials{},
		Transactions:   transactions,
		Secrets:        secrets,
		Coordinator:    coordinator,
		OrganizationID: "00000000-0000-4000-8000-000000000101",
		ProjectID:      "00000000-0000-4000-8000-000000000102",
		CallbackURL:    "https://console.example.invalid/v1/identity/oauth/google/callback",
		TransactionTTL: 10 * time.Minute,
		Now: func() time.Time {
			return now
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	transport, err := NewIdentitySessionCookieTransport(
		IdentitySessionCookieTransportOptions{
			Now:       func() time.Time { return now },
			IntentKey: []byte("0123456789abcdef0123456789abcdef"),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	handler := NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		OAuthFirstLogins: map[string]*OAuthFirstLoginService{
			"google": service,
		},
		OAuthFirstLoginIntents:          transport,
		IdentitySessionReceiptTransport: transport,
	})
	return handler, adapter, transactions, secrets, coordinator, transport
}

func TestOAuthFirstLoginHTTPCompletesCanonicalSessionHandoff(t *testing.T) {
	handler, adapter, transactions, secrets, coordinator, _ :=
		newOAuthFirstLoginHTTPFixture(t)

	start := httptest.NewRequest(
		http.MethodGet,
		"https://console.example.invalid/v1/identity/oauth/google/start",
		nil,
	)
	start.Header.Set("Origin", "https://console.example.invalid")
	start.Header.Set("Sec-Fetch-Site", "same-origin")
	startResponse := httptest.NewRecorder()
	handler.ServeHTTP(startResponse, start)
	if startResponse.Code != http.StatusFound {
		t.Fatalf("start status=%d body=%s", startResponse.Code, startResponse.Body.String())
	}
	if startResponse.Body.Len() != 0 {
		t.Fatalf("OAuth first-login start body must be empty: %q", startResponse.Body.String())
	}
	location := startResponse.Header().Get("Location")
	authorizationURL, err := url.Parse(location)
	if err != nil {
		t.Fatal(err)
	}
	state := authorizationURL.Query().Get("state")
	if state == "" || authorizationURL.Query().Get("code_challenge") == "" ||
		authorizationURL.Query().Get("nonce") == "" {
		t.Fatalf("authorization URL omitted state/PKCE/nonce: %s", location)
	}
	if adapter.lastAuth.CallbackURL !=
		"https://console.example.invalid/v1/identity/oauth/google/callback" {
		t.Fatalf("first-login callback URL was not dedicated: %+v", adapter.lastAuth)
	}
	startCookies := cookiesByName(startResponse.Result().Cookies())
	intent := startCookies[OAuthFirstLoginIntentCookieName]
	if intent == nil || !intent.Secure || !intent.HttpOnly ||
		intent.SameSite != http.SameSiteLaxMode || intent.Path != "/" {
		t.Fatalf("OAuth first-login intent cookie is not hardened: %+v", intent)
	}

	callback := httptest.NewRequest(
		http.MethodGet,
		"https://console.example.invalid/v1/identity/oauth/google/callback?"+
			url.Values{
				"authuser": {"0"},
				"code":     {"provider-code"},
				"iss":      {"https://accounts.google.com"},
				"prompt":   {"none"},
				"scope":    {"openid profile email"},
				"state":    {state},
			}.Encode(),
		nil,
	)
	callback.AddCookie(intent)
	callbackResponse := httptest.NewRecorder()
	handler.ServeHTTP(callbackResponse, callback)
	if callbackResponse.Code != http.StatusSeeOther {
		t.Fatalf(
			"callback status=%d body=%s",
			callbackResponse.Code,
			callbackResponse.Body.String(),
		)
	}
	if callbackResponse.Header().Get("Location") != "/console" ||
		callbackResponse.Body.Len() != 0 ||
		callbackResponse.Header().Get("Content-Type") != "" {
		t.Fatalf(
			"callback handoff is not empty-body 303 /console: headers=%v body=%q",
			callbackResponse.Header(),
			callbackResponse.Body.String(),
		)
	}
	callbackCookies := cookiesByName(callbackResponse.Result().Cookies())
	for _, name := range []string{
		IdentitySessionCookieName,
		IdentityRefreshCookieName,
	} {
		cookie := callbackCookies[name]
		if cookie == nil || !cookie.Secure || !cookie.HttpOnly ||
			cookie.SameSite != http.SameSiteStrictMode || cookie.Path != "/" {
			t.Fatalf("session cookie %s is not hardened: %+v", name, cookie)
		}
	}
	clearedIntent := callbackCookies[OAuthFirstLoginIntentCookieName]
	if clearedIntent == nil || clearedIntent.MaxAge >= 0 || clearedIntent.Value != "" {
		t.Fatalf("OAuth intent was not deleted after success: %+v", clearedIntent)
	}

	if transactions.creates != 1 || transactions.consumes != 1 ||
		secrets.putCalls != 1 || secrets.deleteCalls != 0 ||
		coordinator.calls != 1 {
		t.Fatalf(
			"unexpected first-login side effects: creates=%d consumes=%d puts=%d deletes=%d coordinator=%d",
			transactions.creates,
			transactions.consumes,
			secrets.putCalls,
			secrets.deleteCalls,
			coordinator.calls,
		)
	}
	command := coordinator.command
	if command.Purpose != OAuthPurposeFirstLogin ||
		command.OrganizationID != "00000000-0000-4000-8000-000000000101" ||
		command.ProjectID != "00000000-0000-4000-8000-000000000102" ||
		command.Provider != "google" ||
		command.ProviderSubject != "provider-subject" ||
		command.VerifiedEmail != "first-login@example.invalid" ||
		command.TokenRef != "vault_ref_oauth_first_login" {
		t.Fatalf("coordinator did not receive server-selected canonical input: %+v", command)
	}
	if secrets.lastBinding.TenantID != command.OrganizationID ||
		secrets.lastBinding.ProjectID != command.ProjectID ||
		!strings.HasPrefix(secrets.lastBinding.SessionID, "oauth_first_login:") ||
		secrets.lastBinding.SessionID != secrets.lastBinding.UserID ||
		secrets.lastBinding.UserID != secrets.lastBinding.AccountID {
		t.Fatalf("temporary secret binding is not intent-scoped: %+v", secrets.lastBinding)
	}
	if adapter.lastCode.CodeVerifier == "" ||
		adapter.lastCode.CallbackURL != adapter.lastAuth.CallbackURL ||
		adapter.lastID.Nonce != adapter.lastAuth.Nonce {
		t.Fatalf(
			"callback did not preserve PKCE/nonce/dedicated callback: code=%+v identity=%+v",
			adapter.lastCode,
			adapter.lastID,
		)
	}

	replay := httptest.NewRequest(
		http.MethodGet,
		"https://console.example.invalid/v1/identity/oauth/google/callback?code=provider-code&state="+
			url.QueryEscape(state),
		nil,
	)
	replay.AddCookie(intent)
	replayResponse := httptest.NewRecorder()
	handler.ServeHTTP(replayResponse, replay)
	if replayResponse.Code != http.StatusBadRequest {
		t.Fatalf(
			"callback replay status=%d body=%s",
			replayResponse.Code,
			replayResponse.Body.String(),
		)
	}
	if coordinator.calls != 1 || secrets.putCalls != 1 {
		t.Fatal("callback replay reached canonical mutation or secret storage")
	}
}

func TestStrictOAuthFirstLoginCallbackQueryAllowsOnlyProviderResponseShape(
	t *testing.T,
) {
	t.Parallel()
	cases := []struct {
		name     string
		provider string
		rawQuery string
		ok       bool
	}{
		{
			name:     "google minimal",
			provider: "google",
			rawQuery: "code=provider-code&state=oauth-state",
			ok:       true,
		},
		{
			name:     "google real response extras",
			provider: "google",
			rawQuery: url.Values{
				"authuser": {"0"},
				"code":     {"provider-code"},
				"iss":      {"https://accounts.google.com"},
				"prompt":   {"none"},
				"scope":    {"openid profile email"},
				"state":    {"oauth-state"},
			}.Encode(),
			ok: true,
		},
		{
			name:     "github minimal",
			provider: "github",
			rawQuery: "code=provider-code&state=oauth-state",
			ok:       true,
		},
		{
			name:     "github rejects google extras",
			provider: "github",
			rawQuery: "code=provider-code&state=oauth-state&scope=user",
		},
		{
			name:     "unknown parameter",
			provider: "google",
			rawQuery: "code=provider-code&state=oauth-state&redirect_uri=https%3A%2F%2Fevil.example",
		},
		{
			name:     "duplicate state",
			provider: "google",
			rawQuery: "code=provider-code&state=oauth-state&state=other-state",
		},
		{
			name:     "invalid issuer",
			provider: "google",
			rawQuery: "code=provider-code&state=oauth-state&iss=https%3A%2F%2Fevil.example",
		},
		{
			name:     "invalid authuser",
			provider: "google",
			rawQuery: "code=provider-code&state=oauth-state&authuser=account-zero",
		},
		{
			name:     "invalid prompt",
			provider: "google",
			rawQuery: "code=provider-code&state=oauth-state&prompt=attacker",
		},
		{
			name:     "provider error response is not success",
			provider: "google",
			rawQuery: "error=access_denied&state=oauth-state",
		},
		{
			name:     "malformed encoding",
			provider: "google",
			rawQuery: "code=%zz&state=oauth-state",
		},
		{
			name:     "query too large",
			provider: "google",
			rawQuery: "code=" +
				strings.Repeat("x", maxOAuthFirstLoginCallbackRawQueryLength) +
				"&state=oauth-state",
		},
	}
	for _, testCase := range cases {
		testCase := testCase
		t.Run(testCase.name, func(t *testing.T) {
			t.Parallel()
			request := httptest.NewRequest(
				http.MethodGet,
				"https://console.example.invalid/callback?"+testCase.rawQuery,
				nil,
			)
			code, state, ok := strictOAuthFirstLoginCallbackQuery(
				request,
				testCase.provider,
			)
			if ok != testCase.ok {
				t.Fatalf("ok=%t want=%t", ok, testCase.ok)
			}
			if ok && (code != "provider-code" || state != "oauth-state") {
				t.Fatalf("unexpected accepted callback result")
			}
		})
	}
}

func TestOAuthFirstLoginHTTPRejectsClientSelectedScopeAndPurpose(t *testing.T) {
	handler, _, transactions, secrets, coordinator, _ :=
		newOAuthFirstLoginHTTPFixture(t)

	for _, rawQuery := range []string{
		"tenant_id=attacker",
		"project_id=attacker",
		"account_id=attacker",
		"principal_id=attacker",
		"purpose=binding",
		"redirect_uri=https%3A%2F%2Fevil.example",
	} {
		request := httptest.NewRequest(
			http.MethodGet,
			"https://console.example.invalid/v1/identity/oauth/google/start?"+rawQuery,
			nil,
		)
		request.Header.Set("Origin", "https://console.example.invalid")
		request.Header.Set("Sec-Fetch-Site", "same-origin")
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if response.Code != http.StatusBadRequest {
			t.Fatalf(
				"query %q status=%d body=%s",
				rawQuery,
				response.Code,
				response.Body.String(),
			)
		}
	}
	if transactions.creates != 0 || secrets.putCalls != 0 || coordinator.calls != 0 {
		t.Fatal("client-selected first-login scope reached state or canonical mutation")
	}
}

func TestOAuthFirstLoginHTTPAllowsSameOriginTopLevelNavigationWithoutOrigin(t *testing.T) {
	handler, _, transactions, _, coordinator, _ :=
		newOAuthFirstLoginHTTPFixture(t)

	navigation := httptest.NewRequest(
		http.MethodGet,
		"https://console.example.invalid/v1/identity/oauth/google/start",
		nil,
	)
	navigation.Header.Set("Sec-Fetch-Site", "same-origin")
	navigation.Header.Set("Sec-Fetch-Mode", "navigate")
	navigation.Header.Set("Sec-Fetch-Dest", "document")
	navigation.Header.Set("Referer", "https://console.example.invalid/console")
	navigationResponse := httptest.NewRecorder()
	handler.ServeHTTP(navigationResponse, navigation)
	if navigationResponse.Code != http.StatusFound {
		t.Fatalf(
			"same-origin navigation status=%d body=%s",
			navigationResponse.Code,
			navigationResponse.Body.String(),
		)
	}
	if navigationResponse.Body.Len() != 0 || transactions.creates != 1 || coordinator.calls != 0 {
		t.Fatal("same-origin top-level navigation did not create only the OAuth browser state")
	}
}

func TestOAuthFirstLoginHTTPRejectsMalformedOrCrossSiteTopLevelNavigation(t *testing.T) {
	handler, _, transactions, _, coordinator, _ :=
		newOAuthFirstLoginHTTPFixture(t)

	cases := []struct {
		name    string
		headers map[string]string
	}{
		{
			name: "missing fetch mode",
			headers: map[string]string{
				"Sec-Fetch-Site": "same-origin",
				"Sec-Fetch-Dest": "document",
				"Referer":        "https://console.example.invalid/console",
			},
		},
		{
			name: "non document destination",
			headers: map[string]string{
				"Sec-Fetch-Site": "same-origin",
				"Sec-Fetch-Mode": "navigate",
				"Sec-Fetch-Dest": "iframe",
				"Referer":        "https://console.example.invalid/console",
			},
		},
		{
			name: "cross site",
			headers: map[string]string{
				"Sec-Fetch-Site": "cross-site",
				"Sec-Fetch-Mode": "navigate",
				"Sec-Fetch-Dest": "document",
				"Referer":        "https://evil.example.invalid/",
			},
		},
		{
			name: "forwarded host spoof",
			headers: map[string]string{
				"Sec-Fetch-Site":   "same-origin",
				"Sec-Fetch-Mode":   "navigate",
				"Sec-Fetch-Dest":   "document",
				"Referer":          "https://console.example.invalid/console",
				"X-Forwarded-Host": "evil.example.invalid",
			},
		},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			request := httptest.NewRequest(
				http.MethodGet,
				"https://console.example.invalid/v1/identity/oauth/google/start",
				nil,
			)
			for name, value := range testCase.headers {
				request.Header.Set(name, value)
			}
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != http.StatusForbidden {
				t.Fatalf("navigation status=%d body=%s", response.Code, response.Body.String())
			}
		})
	}
	if transactions.creates != 0 || coordinator.calls != 0 {
		t.Fatal("malformed or cross-site navigation created OAuth state or canonical identity")
	}
}

func TestOAuthFirstLoginHTTPRejectsInsecureTransport(t *testing.T) {
	handler, _, transactions, _, coordinator, _ :=
		newOAuthFirstLoginHTTPFixture(t)

	insecure := httptest.NewRequest(
		http.MethodGet,
		"http://console.example.invalid/v1/identity/oauth/google/start",
		nil,
	)
	insecure.Header.Set("Origin", "https://console.example.invalid")
	insecureResponse := httptest.NewRecorder()
	handler.ServeHTTP(insecureResponse, insecure)
	if insecureResponse.Code != http.StatusUpgradeRequired {
		t.Fatalf(
			"insecure start status=%d body=%s",
			insecureResponse.Code,
			insecureResponse.Body.String(),
		)
	}
	if transactions.creates != 0 || coordinator.calls != 0 {
		t.Fatal("transport/origin failure created OAuth state or canonical identity")
	}
}

func TestOAuthFirstLoginHTTPIntentMismatchFailsBeforeProviderAndMutation(t *testing.T) {
	handler, adapter, transactions, secrets, coordinator, transport :=
		newOAuthFirstLoginHTTPFixture(t)

	start := httptest.NewRequest(
		http.MethodGet,
		"https://console.example.invalid/v1/identity/oauth/google/start",
		nil,
	)
	start.Header.Set("Origin", "https://console.example.invalid")
	start.Header.Set("Sec-Fetch-Site", "same-origin")
	startResponse := httptest.NewRecorder()
	handler.ServeHTTP(startResponse, start)
	if startResponse.Code != http.StatusFound {
		t.Fatalf("start status=%d body=%s", startResponse.Code, startResponse.Body.String())
	}
	authorizationURL, _ := url.Parse(startResponse.Header().Get("Location"))
	state := authorizationURL.Query().Get("state")
	transaction, ok := transactions.transactions["google\x00"+stateSHA256(state)]
	if !ok {
		t.Fatal("first-login transaction was not captured")
	}
	wrongIntentResponse := httptest.NewRecorder()
	wrongIntentRequest := httptest.NewRequest(
		http.MethodGet,
		"https://console.example.invalid/v1/identity/oauth/google/start",
		nil,
	)
	wrongIntentRequest.Header.Set("Origin", "https://console.example.invalid")
	wrongIntentRequest.Header.Set("Sec-Fetch-Site", "same-origin")
	err := transport.IssueOAuthFirstLoginIntent(
		wrongIntentResponse,
		wrongIntentRequest,
		OAuthFirstLoginIntentIssue{
			IntentID:       transaction.IntentID,
			Provider:       "github",
			Purpose:        OAuthPurposeFirstLogin,
			OrganizationID: transaction.OrganizationID,
			ProjectID:      transaction.ProjectID,
			StateHash:      transaction.StateHash,
			ExpiresAt:      transaction.ExpiresAt,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	wrongCookie := cookiesByName(
		wrongIntentResponse.Result().Cookies(),
	)[OAuthFirstLoginIntentCookieName]
	callback := httptest.NewRequest(
		http.MethodGet,
		"https://console.example.invalid/v1/identity/oauth/google/callback?code=provider-code&state="+
			url.QueryEscape(state),
		nil,
	)
	callback.AddCookie(wrongCookie)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, callback)
	if response.Code != http.StatusForbidden {
		t.Fatalf("mismatched intent status=%d body=%s", response.Code, response.Body.String())
	}
	if adapter.lastCode.Code != "" || secrets.putCalls != 0 || coordinator.calls != 0 {
		t.Fatal("intent mismatch reached provider exchange, secret storage, or canonical mutation")
	}
}

func TestOAuthFirstLoginRouteManifestSeparatesPublicLoginFromBinding(t *testing.T) {
	entries := GoRouteManifestEntries()
	byRoute := make(map[string]RouteManifestEntry, len(entries))
	for _, entry := range entries {
		byRoute[entry.Route] = entry
	}
	for _, route := range []string{
		"GET /v1/identity/oauth/google/start",
		"GET /v1/identity/oauth/google/callback",
		"GET /v1/identity/oauth/github/start",
		"GET /v1/identity/oauth/github/callback",
	} {
		entry, ok := byRoute[route]
		if !ok {
			t.Fatalf("route manifest omitted %s", route)
		}
		if entry.AuthRequired || !entry.PublicSafe || entry.Category != "oauth" {
			t.Fatalf("public first-login route metadata is unsafe: %+v", entry)
		}
	}
	for _, route := range []string{
		"GET /v1/projects/{project_id}/oauth/google/start",
		"GET /v1/projects/{project_id}/oauth/github/start",
	} {
		if !byRoute[route].AuthRequired {
			t.Fatalf("authenticated binding route became public: %+v", byRoute[route])
		}
	}
}

func TestOAuthFirstLoginHTTPErrorBodyDoesNotExposeSecrets(t *testing.T) {
	handler, _, _, _, _, _ := newOAuthFirstLoginHTTPFixture(t)
	request := httptest.NewRequest(
		http.MethodGet,
		"https://console.example.invalid/v1/identity/oauth/google/callback?code=secret-code&state=secret-state",
		nil,
	)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	body, err := io.ReadAll(response.Result().Body)
	if err != nil {
		t.Fatal(err)
	}
	var payload map[string]any
	if err := json.Unmarshal(body, &payload); err != nil {
		t.Fatalf("error response is not JSON: %s", body)
	}
	lower := strings.ToLower(string(body))
	for _, forbidden := range []string{
		"secret-code",
		"secret-state",
		"provider-access-token",
		"browser-access-bearer",
		"browser-refresh-bearer",
		"first-login@example.invalid",
	} {
		if strings.Contains(lower, strings.ToLower(forbidden)) {
			t.Fatalf("public error exposed secret %q: %s", forbidden, body)
		}
	}
}
