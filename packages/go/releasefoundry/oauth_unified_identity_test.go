package releasefoundry

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"net/url"
	"reflect"
	"strings"
	"testing"
	"time"
)

func TestOAuthUnifiedIdentitySameCanonicalAccountAcrossGitHubAndGoogle(t *testing.T) {
	store := NewMemoryOAuthStore()
	identity := newUnifiedOAuthTestIdentity(t)
	session := OAuthSession{TenantID: "tenant", UserID: "user", SessionID: "session"}
	setOAuthSessionCanonicalAccount(&session, "account_canonical")

	github := newUnifiedOAuthTestService(t, "github", "github-private-subject", session, store, identity)
	google := newUnifiedOAuthTestService(t, "google", "google-private-subject", session, store, identity)

	githubResult := completeUnifiedOAuthFlow(t, github, "account_canonical")
	googleResult := completeUnifiedOAuthFlow(t, google, "account_canonical")

	if githubResult.Connection.AccountID != "account_canonical" ||
		googleResult.Connection.AccountID != "account_canonical" {
		t.Fatalf("providers did not bind to the canonical account: github=%#v google=%#v",
			githubResult.Connection, googleResult.Connection)
	}
	if githubResult.Connection.Provider != "github" || googleResult.Connection.Provider != "google" {
		t.Fatalf("provider identities collapsed incorrectly: github=%#v google=%#v",
			githubResult.Connection, googleResult.Connection)
	}
	account, err := identity.GetAccount("account_canonical")
	if err != nil {
		t.Fatal(err)
	}
	if account.CredentialCount != 2 {
		t.Fatalf("canonical account credential count=%d want=2 account=%#v", account.CredentialCount, account)
	}
	providers := map[IdentityProvider]bool{}
	for _, credential := range account.Credentials {
		providers[credential.Provider] = true
	}
	if !providers[IdentityProviderGitHub] || !providers[IdentityProviderGoogle] {
		t.Fatalf("canonical account did not retain both provider credentials: %#v", account.Credentials)
	}
}

func TestOAuthUnifiedIdentityRejectsCallerSuppliedAccountTakeover(t *testing.T) {
	identity := newUnifiedOAuthTestIdentity(t)
	session := OAuthSession{TenantID: "tenant", UserID: "user", SessionID: "session"}
	setOAuthSessionCanonicalAccount(&session, "account_canonical")
	service := newUnifiedOAuthTestService(t, "google", "google-private-subject", session, NewMemoryOAuthStore(), identity)
	server := httptest.NewServer(NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		OAuthProviders: map[string]*OAuthService{"google": service},
	}))
	defer server.Close()

	for _, test := range []struct {
		name   string
		method string
		target string
		body   string
	}{
		{
			name:   "query",
			method: http.MethodGet,
			target: "/v1/projects/project/oauth/google/start?tenant_id=tenant&account_id=account_victim",
		},
		{
			name:   "body",
			method: http.MethodPost,
			target: "/v1/projects/project/oauth/google/start",
			body:   `{"tenant_id":"tenant","account_id":"account_victim"}`,
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			request, err := http.NewRequest(test.method, server.URL+test.target, strings.NewReader(test.body))
			if err != nil {
				t.Fatal(err)
			}
			if test.body != "" {
				request.Header.Set("Content-Type", "application/json")
			}
			response, err := http.DefaultClient.Do(request)
			if err != nil {
				t.Fatal(err)
			}
			defer response.Body.Close()

			if response.StatusCode != http.StatusForbidden && response.StatusCode != http.StatusBadRequest {
				var body map[string]any
				_ = json.NewDecoder(response.Body).Decode(&body)
				t.Fatalf("caller-supplied account_id was trusted: status=%d body=%#v", response.StatusCode, body)
			}
		})
	}
}

func TestOAuthUnifiedIdentityRejectsCrossAccountProviderSubjectConflict(t *testing.T) {
	store := NewMemoryOAuthStore()
	identity := newUnifiedOAuthTestIdentity(t)
	ownerSession := OAuthSession{TenantID: "tenant", UserID: "owner-user", SessionID: "owner-session"}
	setOAuthSessionCanonicalAccount(&ownerSession, "account_owner")
	ownerService := newUnifiedOAuthTestService(t, "google", "stable-private-subject", ownerSession, store, identity)

	first := completeUnifiedOAuthFlow(t, ownerService, "account_owner")
	if first.Connection.AccountID != "account_owner" {
		t.Fatalf("unexpected first owner: %#v", first.Connection)
	}

	attackerSession := OAuthSession{TenantID: "tenant", UserID: "attacker-user", SessionID: "attacker-session"}
	setOAuthSessionCanonicalAccount(&attackerSession, "account_attacker")
	attackerService := newUnifiedOAuthTestService(t, "google", "stable-private-subject", attackerSession, store, identity)
	_, err := startAndCallbackUnifiedOAuth(attackerService, "account_attacker")
	if err == nil {
		t.Fatal("same provider subject was silently rebound to a different account")
	}
	var oauthError OAuthError
	if errors.As(err, &oauthError) && oauthError.Status != http.StatusConflict {
		t.Fatalf("cross-account conflict status=%d error=%v", oauthError.Status, oauthError)
	}
}

func TestOAuthUnifiedIdentityPublicResponsesContainNoSubjectTokenOrDigest(t *testing.T) {
	identity := newUnifiedOAuthTestIdentity(t)
	session := OAuthSession{TenantID: "tenant", UserID: "user", SessionID: "session"}
	setOAuthSessionCanonicalAccount(&session, "account_canonical")
	service := newUnifiedOAuthTestService(t, "google", "private-provider-subject", session, NewMemoryOAuthStore(), identity)
	result := completeUnifiedOAuthFlow(t, service, "account_canonical")

	assertUnifiedIdentityPublicPayload(t, result,
		"private-provider-subject",
		"provider-access-token",
		"provider-id-token",
	)
}

type unifiedOAuthTestAdapter struct {
	name    string
	subject string
}

func (adapter unifiedOAuthTestAdapter) Name() string { return adapter.name }

func (adapter unifiedOAuthTestAdapter) SchemaVersion() string {
	return "releasefoundry." + adapter.name + "_oauth.v1"
}

func (adapter unifiedOAuthTestAdapter) ExactScopes() []string {
	return []string{"email", "openid", "profile"}
}

func (adapter unifiedOAuthTestAdapter) AuthorizationURL(request OAuthAuthorizationRequest) (string, error) {
	values := url.Values{
		"state":          {request.State},
		"nonce":          {request.Nonce},
		"code_challenge": {request.CodeChallenge},
	}
	return "https://" + adapter.name + ".example.invalid/authorize?" + values.Encode(), nil
}

func (adapter unifiedOAuthTestAdapter) ExchangeCode(context.Context, OAuthCodeExchangeRequest) (OAuthTokenSet, error) {
	return OAuthTokenSet{
		AccessToken: "provider-access-token",
		IDToken:     "provider-id-token",
		TokenType:   "Bearer",
		Scopes:      adapter.ExactScopes(),
	}, nil
}

func (adapter unifiedOAuthTestAdapter) ResolveIdentity(context.Context, OAuthIdentityRequest) (OAuthProviderIdentity, error) {
	return OAuthProviderIdentity{
		Subject:       adapter.subject,
		DisplayName:   "Unified Identity Test",
		Email:         "private@example.invalid",
		EmailVerified: true,
	}, nil
}

func (adapter unifiedOAuthTestAdapter) RevokeToken(context.Context, OAuthClientCredentials, string) error {
	return nil
}

func newUnifiedOAuthTestService(
	t *testing.T,
	provider string,
	subject string,
	session OAuthSession,
	store *MemoryOAuthStore,
	identity *UnifiedIdentityService,
) *OAuthService {
	t.Helper()
	service, err := NewOAuthService(OAuthServiceOptions{
		Provider:        unifiedOAuthTestAdapter{name: provider, subject: subject},
		SessionResolver: oauthTestSessionResolver{session: session},
		Credentials:     oauthTestCredentials{},
		Transactions:    store,
		Secrets:         store,
		Connections:     store,
		IdentityBridge:  UnifiedIdentityOAuthBridge{Identity: identity},
		CallbackURL:     "http://localhost:8787/oauth/" + provider + "/callback",
		TransactionTTL:  time.Minute,
		Now: func() time.Time {
			return time.Date(2026, 7, 10, 12, 0, 0, 0, time.UTC)
		},
		Random: &identitySequenceReader{},
	})
	if err != nil {
		t.Fatalf("new %s OAuth service: %v", provider, err)
	}
	return service
}

func newUnifiedOAuthTestIdentity(t *testing.T) *UnifiedIdentityService {
	t.Helper()
	identity, err := NewUnifiedIdentityService(UnifiedIdentityServiceOptions{
		Now: func() time.Time {
			return time.Date(2026, 7, 10, 12, 0, 0, 0, time.UTC)
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	return identity
}

func completeUnifiedOAuthFlow(t *testing.T, service *OAuthService, accountID string) OAuthCallbackResult {
	t.Helper()
	result, err := startAndCallbackUnifiedOAuth(service, accountID)
	if err != nil {
		t.Fatalf("complete %s OAuth flow: %v", service.ProviderName(), err)
	}
	return result
}

func startAndCallbackUnifiedOAuth(service *OAuthService, accountID string) (OAuthCallbackResult, error) {
	request := httptest.NewRequest(http.MethodPost, "/oauth", nil)
	start, err := service.Start(context.Background(), request, "tenant", "project", accountID)
	if err != nil {
		return OAuthCallbackResult{}, err
	}
	authorizeURL, err := url.Parse(start.AuthorizationURL)
	if err != nil {
		return OAuthCallbackResult{}, err
	}
	state := authorizeURL.Query().Get("state")
	return service.Callback(context.Background(), request, "authorization-code", state)
}

func setOAuthSessionCanonicalAccount(session *OAuthSession, accountID string) {
	value := reflect.ValueOf(session).Elem()
	field := value.FieldByName("AccountID")
	if field.IsValid() && field.CanSet() && field.Kind() == reflect.String {
		field.SetString(accountID)
	}
}
