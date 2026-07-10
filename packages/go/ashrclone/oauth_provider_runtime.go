package ashrclone

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

type EnvOAuthCredentialsProvider struct {
	LookupEnv func(string) (string, bool)
}

func (provider EnvOAuthCredentialsProvider) OAuthCredentials(_ context.Context, providerName string) (OAuthClientCredentials, error) {
	lookup := provider.LookupEnv
	if lookup == nil {
		return OAuthClientCredentials{}, fmt.Errorf("OAuth environment lookup is not configured")
	}
	prefix := "ASHR_" + strings.ToUpper(strings.TrimSpace(providerName)) + "_OAUTH_"
	clientID, clientIDOK := lookup(prefix + "CLIENT_ID")
	clientSecret, clientSecretOK := lookup(prefix + "CLIENT_SECRET")
	if !clientIDOK || !clientSecretOK || strings.TrimSpace(clientID) == "" || strings.TrimSpace(clientSecret) == "" {
		return OAuthClientCredentials{}, fmt.Errorf("%s OAuth credentials are not configured", providerName)
	}
	if strings.TrimSpace(clientID) == strings.TrimSpace(clientSecret) {
		return OAuthClientCredentials{}, fmt.Errorf("%s OAuth client secret must differ from client ID", providerName)
	}
	return OAuthClientCredentials{ClientID: strings.TrimSpace(clientID), ClientSecret: clientSecret}, nil
}

type LocalhostDevOAuthSessionResolver struct {
	Enabled   bool
	TenantID  string
	UserID    string
	SessionID string
	AccountID string
	Revoked   func(context.Context, string) (bool, error)
}

func (resolver LocalhostDevOAuthSessionResolver) ResolveOAuthSession(ctx context.Context, request *http.Request) (OAuthSession, error) {
	if !resolver.Enabled {
		return OAuthSession{}, fmt.Errorf("localhost development session resolver is disabled")
	}
	if request == nil || !isLoopbackRequest(request) {
		return OAuthSession{}, fmt.Errorf("localhost development session resolver rejected a non-loopback request")
	}
	session := OAuthSession{
		TenantID: strings.TrimSpace(resolver.TenantID), UserID: strings.TrimSpace(resolver.UserID),
		SessionID: strings.TrimSpace(resolver.SessionID), AccountID: strings.TrimSpace(resolver.AccountID),
	}
	if session.TenantID == "" || session.UserID == "" || session.SessionID == "" || session.AccountID == "" {
		return OAuthSession{}, fmt.Errorf("localhost development session identity is incomplete")
	}
	if resolver.Revoked != nil {
		revoked, err := resolver.Revoked(ctx, session.SessionID)
		if err != nil {
			return OAuthSession{}, fmt.Errorf("localhost development session status is unavailable")
		}
		session.Revoked = revoked
	}
	return session, nil
}

type GoogleOAuthEnvRuntimeOptions struct {
	LookupEnv      func(string) (string, bool)
	HTTPClient     OAuthHTTPClient
	IdentityBridge OAuthIdentityBridge
	Identity       *UnifiedIdentityService
	Now            func() time.Time
}

func NewGoogleOAuthServiceFromEnv(options GoogleOAuthEnvRuntimeOptions) (*OAuthService, error) {
	lookup := options.LookupEnv
	if lookup == nil {
		return nil, fmt.Errorf("Google OAuth environment lookup is required")
	}
	if !envBool(lookup, "ASHR_GOOGLE_OAUTH_ENABLED") {
		return nil, nil
	}
	if !envBool(lookup, "ASHR_GOOGLE_OAUTH_DEV_SESSION_ENABLED") {
		return nil, fmt.Errorf("Google OAuth requires an explicit session resolver; localhost dev session is disabled")
	}
	callbackURL := envValue(lookup, "ASHR_GOOGLE_OAUTH_CALLBACK_URL")
	parsedCallback, err := parseProviderLocalhostCallbackURL("Google", "google", callbackURL)
	if err != nil {
		return nil, err
	}
	ttl, err := oauthEnvDurationSeconds(lookup, "ASHR_GOOGLE_OAUTH_TRANSACTION_TTL_SECONDS", 10*time.Minute, 30, 3600)
	if err != nil {
		return nil, err
	}
	upstreamTimeout, err := oauthEnvDurationSeconds(lookup, "ASHR_GOOGLE_OAUTH_UPSTREAM_TIMEOUT_SECONDS", 10*time.Second, 1, 60)
	if err != nil {
		return nil, err
	}
	credentials := EnvOAuthCredentialsProvider{LookupEnv: lookup}
	if _, err := credentials.OAuthCredentials(context.Background(), "google"); err != nil {
		return nil, fmt.Errorf("Google OAuth credentials are unavailable")
	}
	provider, err := NewGoogleOIDCProvider(GoogleOIDCOptions{
		HTTPClient:      options.HTTPClient,
		AuthorizeURL:    firstNonEmpty(envValue(lookup, "ASHR_GOOGLE_OAUTH_AUTHORIZE_URL"), defaultGoogleAuthorizeURL),
		TokenURL:        firstNonEmpty(envValue(lookup, "ASHR_GOOGLE_OAUTH_TOKEN_URL"), defaultGoogleTokenURL),
		RevokeURL:       firstNonEmpty(envValue(lookup, "ASHR_GOOGLE_OAUTH_REVOKE_URL"), defaultGoogleRevokeURL),
		JWKSURL:         firstNonEmpty(envValue(lookup, "ASHR_GOOGLE_OAUTH_JWKS_URL"), defaultGoogleJWKSURL),
		UpstreamTimeout: upstreamTimeout,
	})
	if err != nil {
		return nil, err
	}
	store := NewMemoryOAuthStore()
	var coordinator OAuthIdentityCoordinator
	if options.Identity != nil {
		coordinator, err = NewMemoryOAuthIdentityCoordinator(options.Identity, store)
		if err != nil {
			return nil, err
		}
	}
	return NewOAuthService(OAuthServiceOptions{
		Provider: provider,
		SessionResolver: LocalhostDevOAuthSessionResolver{
			Enabled: true, TenantID: envValue(lookup, "ASHR_GOOGLE_OAUTH_DEV_TENANT_ID"),
			UserID:    envValue(lookup, "ASHR_GOOGLE_OAUTH_DEV_USER_ID"),
			SessionID: envValue(lookup, "ASHR_GOOGLE_OAUTH_DEV_SESSION_ID"),
			AccountID: envValue(lookup, "ASHR_GOOGLE_OAUTH_DEV_ACCOUNT_ID"),
		},
		Credentials: credentials, Transactions: store, Secrets: store, Connections: store,
		IdentityBridge:      options.IdentityBridge,
		IdentityCoordinator: coordinator,
		CallbackURL:         parsedCallback.String(), TransactionTTL: ttl, Now: options.Now,
	})
}

func parseProviderLocalhostCallbackURL(providerName, providerPath, raw string) (*url.URL, error) {
	callback, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || callback.Scheme != "http" || callback.Host == "" || callback.User != nil ||
		callback.RawQuery != "" || callback.Fragment != "" {
		return nil, fmt.Errorf("%s OAuth callback URL must be an http localhost URL without query or fragment", providerName)
	}
	host := callback.Hostname()
	ip := net.ParseIP(host)
	if !strings.EqualFold(host, "localhost") && (ip == nil || !ip.IsLoopback()) {
		return nil, fmt.Errorf("%s OAuth callback URL must use localhost or a loopback IP", providerName)
	}
	if callback.Path != "/oauth/"+providerPath+"/callback" {
		return nil, fmt.Errorf("%s OAuth callback URL path must be /oauth/%s/callback", providerName, providerPath)
	}
	return callback, nil
}

func oauthEnvDurationSeconds(lookup func(string) (string, bool), key string, fallback time.Duration, minimum, maximum int) (time.Duration, error) {
	raw := envValue(lookup, key)
	if raw == "" {
		return fallback, nil
	}
	seconds, err := strconv.Atoi(raw)
	if err != nil || seconds < minimum || seconds > maximum {
		return 0, fmt.Errorf("%s must be between %d and %d", key, minimum, maximum)
	}
	return time.Duration(seconds) * time.Second, nil
}
