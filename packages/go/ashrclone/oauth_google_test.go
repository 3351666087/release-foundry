package ashrclone

import (
	"context"
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"math/big"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"
)

type oauthTestRoundTripper func(*http.Request) (*http.Response, error)

func (transport oauthTestRoundTripper) RoundTrip(request *http.Request) (*http.Response, error) {
	return transport(request)
}

func TestGoogleOIDCAuthorizationUsesExactScopesPKCEAndNonce(t *testing.T) {
	provider := newTestGoogleProvider(t, nil)
	authorizationURL, err := provider.AuthorizationURL(OAuthAuthorizationRequest{
		ClientID: "client-id", CallbackURL: "http://localhost:8787/oauth/google/callback",
		State: "state", CodeChallenge: "challenge", Nonce: "nonce",
		Scopes: []string{"profile", "openid", "email"},
	})
	if err != nil {
		t.Fatal(err)
	}
	parsed, err := url.Parse(authorizationURL)
	if err != nil {
		t.Fatal(err)
	}
	query := parsed.Query()
	for name, expected := range map[string]string{
		"client_id": "client-id", "redirect_uri": "http://localhost:8787/oauth/google/callback",
		"response_type": "code", "scope": "email openid profile", "state": "state",
		"nonce": "nonce", "code_challenge": "challenge", "code_challenge_method": "S256",
	} {
		if query.Get(name) != expected {
			t.Fatalf("%s=%q, want %q", name, query.Get(name), expected)
		}
	}
	if _, err := provider.AuthorizationURL(OAuthAuthorizationRequest{
		ClientID: "client-id", CallbackURL: "http://localhost:8787/oauth/google/callback",
		State: "state", CodeChallenge: "challenge", Nonce: "nonce",
		Scopes: []string{"openid", "email"},
	}); err == nil {
		t.Fatal("expected scope reduction to be rejected")
	}
	if _, err := provider.AuthorizationURL(OAuthAuthorizationRequest{
		ClientID: "client-id", CallbackURL: "http://localhost:8787/oauth/google/callback",
		State: "state", CodeChallenge: "challenge", Nonce: "nonce",
		Scopes: []string{"openid", "email", "profile", "calendar.readonly"},
	}); err == nil {
		t.Fatal("expected scope escalation to be rejected")
	}
}

func TestGoogleOIDCExchangeRequiresExactScopesAndIDToken(t *testing.T) {
	tests := []struct {
		name      string
		scope     string
		idToken   string
		wantError string
	}{
		{name: "exact reordered", scope: "profile email openid", idToken: "header.claim.signature"},
		{
			name:    "official aliases and short names",
			scope:   "email profile https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/userinfo.email openid",
			idToken: "header.claim.signature",
		},
		{
			name:    "official aliases only",
			scope:   "https://www.googleapis.com/auth/userinfo.profile openid https://www.googleapis.com/auth/userinfo.email",
			idToken: "header.claim.signature",
		},
		{name: "missing", scope: "openid email", idToken: "header.claim.signature", wantError: "google_scope_mismatch"},
		{name: "unexpected", scope: "openid email profile drive", idToken: "header.claim.signature", wantError: "google_scope_mismatch"},
		{name: "missing id token", scope: "openid email profile", wantError: "google_token_exchange_failed"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			client := &http.Client{Transport: oauthTestRoundTripper(func(request *http.Request) (*http.Response, error) {
				if deadline, ok := request.Context().Deadline(); !ok || time.Until(deadline) > time.Second {
					t.Fatal("token request did not carry the configured upstream deadline")
				}
				if err := request.ParseForm(); err != nil {
					t.Fatal(err)
				}
				for name, expected := range map[string]string{
					"client_id": "client-id", "client_secret": "client-secret", "code": "code",
					"redirect_uri": "http://localhost/callback", "code_verifier": "verifier",
					"grant_type": "authorization_code",
				} {
					if request.Form.Get(name) != expected {
						t.Fatalf("%s=%q, want %q", name, request.Form.Get(name), expected)
					}
				}
				payload, _ := json.Marshal(map[string]string{
					"access_token": "access-token", "token_type": "Bearer", "scope": test.scope, "id_token": test.idToken,
				})
				return oauthTestResponse(request, http.StatusOK, string(payload)), nil
			})}
			provider := newTestGoogleProvider(t, client)
			tokenSet, err := provider.ExchangeCode(context.Background(), OAuthCodeExchangeRequest{
				Credentials: OAuthClientCredentials{ClientID: "client-id", ClientSecret: "client-secret"},
				CallbackURL: "http://localhost/callback", Code: "code", CodeVerifier: "verifier",
			})
			if test.wantError == "" {
				if err != nil || tokenSet.AccessToken == "" || tokenSet.IDToken == "" {
					t.Fatalf("exchange failed: token=%+v err=%v", tokenSet, err)
				}
				return
			}
			var oauthErr OAuthError
			if err == nil || !errors.As(err, &oauthErr) || oauthErr.Code != test.wantError {
				t.Fatalf("expected %s, got %#v", test.wantError, err)
			}
		})
	}
}

func TestGoogleOIDCIdentityValidation(t *testing.T) {
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 7, 10, 5, 6, 7, 0, time.UTC)
	jwks := googleTestJWKS(t, "key-1", &privateKey.PublicKey)
	client := &http.Client{Transport: oauthTestRoundTripper(func(request *http.Request) (*http.Response, error) {
		if request.URL.String() != "https://google.test/jwks" {
			t.Fatalf("unexpected request: %s", request.URL)
		}
		return oauthTestResponse(request, http.StatusOK, jwks), nil
	})}
	provider := newTestGoogleProvider(t, client)
	baseClaims := map[string]any{
		"iss": "https://accounts.google.com", "aud": "client-id", "sub": "google-subject",
		"exp": now.Add(time.Hour).Unix(), "iat": now.Add(-time.Minute).Unix(), "nonce": "expected-nonce",
		"email": "verified@example.invalid", "email_verified": true, "name": "Verified User",
	}
	tests := []struct {
		name   string
		mutate func(map[string]any)
		wantOK bool
	}{
		{name: "valid", wantOK: true},
		{name: "issuer", mutate: func(claims map[string]any) { claims["iss"] = "https://evil.invalid" }},
		{name: "audience", mutate: func(claims map[string]any) { claims["aud"] = "other-client" }},
		{name: "multiple audience", mutate: func(claims map[string]any) { claims["aud"] = []string{"client-id", "other-client"} }},
		{name: "nonce", mutate: func(claims map[string]any) { claims["nonce"] = "replayed-nonce" }},
		{name: "email unverified", mutate: func(claims map[string]any) { claims["email_verified"] = false }},
		{name: "email absent", mutate: func(claims map[string]any) { delete(claims, "email") }},
		{name: "expired", mutate: func(claims map[string]any) { claims["exp"] = now.Add(-time.Minute).Unix() }},
		{name: "future issued", mutate: func(claims map[string]any) { claims["iat"] = now.Add(time.Hour).Unix() }},
		{name: "excessive lifetime", mutate: func(claims map[string]any) {
			claims["iat"] = now.Add(-time.Minute).Unix()
			claims["exp"] = now.Add(3 * time.Hour).Unix()
		}},
		{name: "empty subject", mutate: func(claims map[string]any) { claims["sub"] = "" }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			claims := cloneOAuthClaims(baseClaims)
			if test.mutate != nil {
				test.mutate(claims)
			}
			token := signGoogleTestIDToken(t, privateKey, "key-1", claims)
			identity, err := provider.ResolveIdentity(context.Background(), OAuthIdentityRequest{
				TokenSet: OAuthTokenSet{IDToken: token}, Nonce: "expected-nonce", ClientID: "client-id", Now: now,
			})
			if test.wantOK {
				if err != nil || identity.Subject != "google-subject" || !identity.EmailVerified {
					t.Fatalf("identity validation failed: identity=%+v err=%v", identity, err)
				}
				return
			}
			var oauthErr OAuthError
			if err == nil || !errors.As(err, &oauthErr) || oauthErr.Code != "google_identity_validation_failed" {
				t.Fatalf("expected identity validation failure, got %#v", err)
			}
		})
	}
}

func TestGoogleOIDCRejectsInvalidSignatureAndUnknownKey(t *testing.T) {
	trustedKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	attackerKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	client := &http.Client{Transport: oauthTestRoundTripper(func(request *http.Request) (*http.Response, error) {
		return oauthTestResponse(request, http.StatusOK, googleTestJWKS(t, "trusted", &trustedKey.PublicKey)), nil
	})}
	provider := newTestGoogleProvider(t, client)
	claims := map[string]any{
		"iss": "https://accounts.google.com", "aud": "client-id", "sub": "subject",
		"exp": now.Add(time.Hour).Unix(), "iat": now.Unix(), "nonce": "nonce",
		"email": "verified@example.invalid", "email_verified": true,
	}
	for _, test := range []struct {
		name string
		kid  string
		key  *rsa.PrivateKey
	}{
		{name: "invalid signature", kid: "trusted", key: attackerKey},
		{name: "unknown key", kid: "unknown", key: attackerKey},
	} {
		t.Run(test.name, func(t *testing.T) {
			_, err := provider.ResolveIdentity(context.Background(), OAuthIdentityRequest{
				TokenSet: OAuthTokenSet{IDToken: signGoogleTestIDToken(t, test.key, test.kid, claims)},
				Nonce:    "nonce", ClientID: "client-id", Now: now,
			})
			if err == nil {
				t.Fatal("expected ID token rejection")
			}
		})
	}
}

func TestGoogleOIDCUpstreamTimeoutCancelsBlockedRequests(t *testing.T) {
	client := &http.Client{Transport: oauthTestRoundTripper(func(request *http.Request) (*http.Response, error) {
		<-request.Context().Done()
		return nil, request.Context().Err()
	})}
	provider, err := NewGoogleOIDCProvider(GoogleOIDCOptions{
		HTTPClient: client, AuthorizeURL: "https://google.test/authorize", TokenURL: "https://google.test/token",
		RevokeURL: "https://google.test/revoke", JWKSURL: "https://google.test/jwks",
		UpstreamTimeout: 20 * time.Millisecond,
	})
	if err != nil {
		t.Fatal(err)
	}
	started := time.Now()
	_, err = provider.ExchangeCode(context.Background(), OAuthCodeExchangeRequest{
		Credentials: OAuthClientCredentials{ClientID: "client-id", ClientSecret: "client-secret"},
		CallbackURL: "http://localhost/callback", Code: "code", CodeVerifier: "verifier",
	})
	if err == nil || time.Since(started) > time.Second {
		t.Fatalf("blocked upstream was not promptly cancelled: duration=%s err=%v", time.Since(started), err)
	}
}

func TestProviderNeutralOAuthServiceCarriesNonceAndMinimizesConnection(t *testing.T) {
	now := time.Date(2026, 7, 10, 5, 6, 7, 0, time.UTC)
	store := NewMemoryOAuthStore()
	adapter := &oauthTestProvider{}
	service, err := NewOAuthService(OAuthServiceOptions{
		Provider:        adapter,
		SessionResolver: oauthTestSessionResolver{session: OAuthSession{TenantID: "tenant", UserID: "user", SessionID: "session", AccountID: "account"}},
		Credentials:     oauthTestCredentials{}, Transactions: store, Secrets: store, Connections: store,
		CallbackURL: "http://localhost:8787/oauth/google/callback", TransactionTTL: time.Minute,
		Now: func() time.Time { return now },
	})
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodPost, "http://localhost/start", nil)
	start, err := service.Start(context.Background(), request, "tenant", "project", "account")
	if err != nil {
		t.Fatal(err)
	}
	parsed, _ := url.Parse(start.AuthorizationURL)
	state := parsed.Query().Get("state")
	if adapter.authorizationNonce == "" || state == "" {
		t.Fatal("provider-neutral start omitted nonce or state")
	}
	callback, err := service.Callback(context.Background(), request, "code", state)
	if err != nil {
		t.Fatal(err)
	}
	if adapter.identityNonce != adapter.authorizationNonce {
		t.Fatalf("nonce was not bound across callback: start=%q callback=%q", adapter.authorizationNonce, adapter.identityNonce)
	}
	payload, err := json.Marshal(callback.Connection)
	if err != nil {
		t.Fatal(err)
	}
	text := string(payload)
	for _, forbidden := range []string{"tenant", "project", "session", "user", "verified@example.invalid", "access-token", "_oauth_ref_"} {
		if strings.Contains(text, forbidden) {
			t.Fatalf("public connection leaked %q: %s", forbidden, text)
		}
	}
}

func TestLoopbackValidationRejectsAmbiguousHostAndProxyHeaders(t *testing.T) {
	resolver := LocalhostDevGitHubOAuthSessionResolver{Enabled: true, TenantID: "tenant", UserID: "user", SessionID: "session", AccountID: "account"}
	for _, test := range []struct {
		name   string
		host   string
		header string
	}{
		{name: "userinfo host", host: "localhost@evil.invalid"},
		{name: "comma host", host: "localhost,evil.invalid"},
		{name: "ambiguous port", host: "localhost:8787:9999"},
		{name: "forwarded proto", host: "localhost:8787", header: "X-Forwarded-Proto"},
		{name: "real ip", host: "localhost:8787", header: "X-Real-IP"},
	} {
		t.Run(test.name, func(t *testing.T) {
			request := httptest.NewRequest(http.MethodGet, "http://localhost:8787/oauth/google/callback", nil)
			request.RemoteAddr = "127.0.0.1:4242"
			request.Host = test.host
			if test.header != "" {
				request.Header.Set(test.header, "127.0.0.1")
			}
			if _, err := resolver.ResolveGitHubOAuthSession(context.Background(), request); err == nil {
				t.Fatal("expected loopback validation rejection")
			}
		})
	}
}

func TestGoogleOAuthEnvRuntimeFailsClosedAndRedactsCredentials(t *testing.T) {
	env := map[string]string{
		"ASHR_GOOGLE_OAUTH_ENABLED": "true", "ASHR_GOOGLE_OAUTH_DEV_SESSION_ENABLED": "true",
		"ASHR_GOOGLE_OAUTH_CALLBACK_URL":  "http://localhost:8787/oauth/google/callback",
		"ASHR_GOOGLE_OAUTH_DEV_TENANT_ID": "tenant", "ASHR_GOOGLE_OAUTH_DEV_USER_ID": "user",
		"ASHR_GOOGLE_OAUTH_DEV_SESSION_ID": "session",
		"ASHR_GOOGLE_OAUTH_CLIENT_ID":      "same-sensitive-value", "ASHR_GOOGLE_OAUTH_CLIENT_SECRET": "same-sensitive-value",
	}
	lookup := func(key string) (string, bool) { value, ok := env[key]; return value, ok }
	_, err := NewGoogleOAuthServiceFromEnv(GoogleOAuthEnvRuntimeOptions{LookupEnv: lookup})
	if err == nil || strings.Contains(err.Error(), "same-sensitive-value") {
		t.Fatalf("expected redacted unequal-credential failure, got %v", err)
	}
	env["ASHR_GOOGLE_OAUTH_CLIENT_SECRET"] = "different-sensitive-value"
	delete(env, "ASHR_GOOGLE_OAUTH_DEV_SESSION_ENABLED")
	if _, err := NewGoogleOAuthServiceFromEnv(GoogleOAuthEnvRuntimeOptions{LookupEnv: lookup}); err == nil {
		t.Fatal("expected explicit development session enablement")
	}
	env["ASHR_GOOGLE_OAUTH_DEV_SESSION_ENABLED"] = "true"
	env["ASHR_GOOGLE_OAUTH_CALLBACK_URL"] = "http://localhost:8787/oauth/google/callback?code=leak"
	if _, err := NewGoogleOAuthServiceFromEnv(GoogleOAuthEnvRuntimeOptions{LookupEnv: lookup}); err == nil {
		t.Fatal("expected callback query to be rejected")
	}
}

func TestGitHubOAuthCustomClientStillReceivesUpstreamDeadline(t *testing.T) {
	client := &http.Client{Transport: oauthTestRoundTripper(func(request *http.Request) (*http.Response, error) {
		deadline, ok := request.Context().Deadline()
		if !ok || time.Until(deadline) > 100*time.Millisecond {
			t.Fatal("GitHub upstream request did not carry service deadline")
		}
		return oauthTestResponse(request, http.StatusOK, `{"access_token":"token","token_type":"bearer","scope":"read:user"}`), nil
	})}
	service, err := NewGitHubOAuthService(GitHubOAuthOptions{
		SessionResolver: testGitHubOAuthSessionResolver{session: GitHubOAuthSession{TenantID: "tenant", UserID: "user", SessionID: "session", AccountID: "account"}},
		Credentials:     testGitHubOAuthCredentials{}, Transactions: NewMemoryGitHubOAuthStore(),
		Secrets: NewMemoryGitHubOAuthStore(), Connections: NewMemoryGitHubOAuthStore(), HTTPClient: client,
		AuthorizeURL: "http://github.test/authorize", TokenURL: "http://github.test/token", APIURL: "http://github.test",
		CallbackURL: "http://localhost:8787/oauth/github/callback", UpstreamTimeout: 50 * time.Millisecond,
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.exchangeCode(context.Background(), GitHubOAuthCredentials{
		ClientID: "client-id", ClientSecret: "client-secret",
	}, "code", "verifier"); err != nil {
		t.Fatal(err)
	}
}

type oauthTestSessionResolver struct{ session OAuthSession }

func (resolver oauthTestSessionResolver) ResolveOAuthSession(context.Context, *http.Request) (OAuthSession, error) {
	return resolver.session, nil
}

type oauthTestCredentials struct{}

func (oauthTestCredentials) OAuthCredentials(context.Context, string) (OAuthClientCredentials, error) {
	return OAuthClientCredentials{ClientID: "client-id", ClientSecret: "client-secret"}, nil
}

type oauthTestProvider struct {
	authorizationNonce string
	identityNonce      string
}

func (provider *oauthTestProvider) Name() string          { return "google" }
func (provider *oauthTestProvider) SchemaVersion() string { return GoogleOAuthSchemaVersion }
func (provider *oauthTestProvider) ExactScopes() []string {
	return []string{"email", "openid", "profile"}
}
func (provider *oauthTestProvider) RevokeToken(context.Context, OAuthClientCredentials, string) error {
	return nil
}
func (provider *oauthTestProvider) AuthorizationURL(request OAuthAuthorizationRequest) (string, error) {
	provider.authorizationNonce = request.Nonce
	return "https://accounts.google.test/authorize?state=" + url.QueryEscape(request.State), nil
}
func (provider *oauthTestProvider) ExchangeCode(context.Context, OAuthCodeExchangeRequest) (OAuthTokenSet, error) {
	return OAuthTokenSet{AccessToken: "access-token", TokenType: "Bearer", Scopes: provider.ExactScopes(), IDToken: "id-token"}, nil
}
func (provider *oauthTestProvider) ResolveIdentity(_ context.Context, request OAuthIdentityRequest) (OAuthProviderIdentity, error) {
	provider.identityNonce = request.Nonce
	return OAuthProviderIdentity{
		Subject: "subject", DisplayName: "Verified User",
		Email: "verified@example.invalid", EmailVerified: true,
	}, nil
}

func newTestGoogleProvider(t *testing.T, client OAuthHTTPClient) *GoogleOIDCProvider {
	t.Helper()
	provider, err := NewGoogleOIDCProvider(GoogleOIDCOptions{
		HTTPClient: client, AuthorizeURL: "https://google.test/authorize", TokenURL: "https://google.test/token",
		RevokeURL: "https://google.test/revoke", JWKSURL: "https://google.test/jwks",
		UpstreamTimeout: 500 * time.Millisecond,
	})
	if err != nil {
		t.Fatal(err)
	}
	return provider
}

func oauthTestResponse(request *http.Request, status int, body string) *http.Response {
	return &http.Response{
		StatusCode: status, Header: make(http.Header), Body: io.NopCloser(strings.NewReader(body)), Request: request,
	}
}

func googleTestJWKS(t *testing.T, kid string, key *rsa.PublicKey) string {
	t.Helper()
	exponent := big.NewInt(int64(key.E)).Bytes()
	payload, err := json.Marshal(map[string]any{"keys": []map[string]string{{
		"kid": kid, "kty": "RSA", "alg": "RS256", "use": "sig",
		"n": base64.RawURLEncoding.EncodeToString(key.N.Bytes()),
		"e": base64.RawURLEncoding.EncodeToString(exponent),
	}}})
	if err != nil {
		t.Fatal(err)
	}
	return string(payload)
}

func signGoogleTestIDToken(t *testing.T, key *rsa.PrivateKey, kid string, claims map[string]any) string {
	t.Helper()
	headerBytes, _ := json.Marshal(map[string]string{"alg": "RS256", "kid": kid, "typ": "JWT"})
	claimBytes, _ := json.Marshal(claims)
	header := base64.RawURLEncoding.EncodeToString(headerBytes)
	payload := base64.RawURLEncoding.EncodeToString(claimBytes)
	signingInput := header + "." + payload
	digest := sha256.Sum256([]byte(signingInput))
	signature, err := rsa.SignPKCS1v15(rand.Reader, key, crypto.SHA256, digest[:])
	if err != nil {
		t.Fatal(err)
	}
	return signingInput + "." + base64.RawURLEncoding.EncodeToString(signature)
}

func cloneOAuthClaims(source map[string]any) map[string]any {
	cloned := make(map[string]any, len(source))
	for key, value := range source {
		cloned[key] = value
	}
	return cloned
}
