package releasefoundry

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

type EnvGitHubOAuthCredentialsProvider struct {
	LookupEnv func(string) (string, bool)
}

func (provider EnvGitHubOAuthCredentialsProvider) GitHubOAuthCredentials(context.Context) (GitHubOAuthCredentials, error) {
	lookup := provider.LookupEnv
	if lookup == nil {
		return GitHubOAuthCredentials{}, fmt.Errorf("GitHub OAuth environment lookup is not configured")
	}
	clientID, clientIDOK := lookup("RELEASEFOUNDRY_GITHUB_OAUTH_CLIENT_ID")
	clientSecret, clientSecretOK := lookup("RELEASEFOUNDRY_GITHUB_OAUTH_CLIENT_SECRET")
	if !clientIDOK || !clientSecretOK || strings.TrimSpace(clientID) == "" || strings.TrimSpace(clientSecret) == "" {
		return GitHubOAuthCredentials{}, fmt.Errorf("GitHub OAuth credentials are not configured")
	}
	if strings.TrimSpace(clientID) == strings.TrimSpace(clientSecret) {
		return GitHubOAuthCredentials{}, fmt.Errorf("GitHub OAuth client secret must differ from client ID")
	}
	return GitHubOAuthCredentials{ClientID: strings.TrimSpace(clientID), ClientSecret: clientSecret}, nil
}

type LocalhostDevGitHubOAuthSessionResolver struct {
	Enabled   bool
	TenantID  string
	UserID    string
	SessionID string
	AccountID string
	Revoked   func(context.Context, string) (bool, error)
}

func (resolver LocalhostDevGitHubOAuthSessionResolver) ResolveGitHubOAuthSession(ctx context.Context, request *http.Request) (GitHubOAuthSession, error) {
	if !resolver.Enabled {
		return GitHubOAuthSession{}, fmt.Errorf("localhost development session resolver is disabled")
	}
	if request == nil || !isLoopbackRequest(request) {
		return GitHubOAuthSession{}, fmt.Errorf("localhost development session resolver rejected a non-loopback request")
	}
	session := GitHubOAuthSession{
		TenantID:  strings.TrimSpace(resolver.TenantID),
		UserID:    strings.TrimSpace(resolver.UserID),
		SessionID: strings.TrimSpace(resolver.SessionID),
		AccountID: strings.TrimSpace(resolver.AccountID),
	}
	if session.TenantID == "" || session.UserID == "" || session.SessionID == "" || session.AccountID == "" {
		return GitHubOAuthSession{}, fmt.Errorf("localhost development session identity is incomplete")
	}
	if resolver.Revoked != nil {
		revoked, err := resolver.Revoked(ctx, session.SessionID)
		if err != nil {
			return GitHubOAuthSession{}, fmt.Errorf("localhost development session status is unavailable")
		}
		session.Revoked = revoked
	}
	return session, nil
}

func isLoopbackRequest(request *http.Request) bool {
	if request == nil || strings.TrimSpace(request.Header.Get("Forwarded")) != "" ||
		strings.TrimSpace(request.Header.Get("X-Forwarded-For")) != "" ||
		strings.TrimSpace(request.Header.Get("X-Forwarded-Host")) != "" ||
		strings.TrimSpace(request.Header.Get("X-Forwarded-Proto")) != "" ||
		strings.TrimSpace(request.Header.Get("X-Real-IP")) != "" {
		return false
	}
	remoteHost, _, err := net.SplitHostPort(request.RemoteAddr)
	if err != nil {
		return false
	}
	remoteIP := net.ParseIP(strings.Trim(remoteHost, "[]"))
	if remoteIP == nil || !remoteIP.IsLoopback() {
		return false
	}
	host := strings.TrimSpace(request.Host)
	if host == "" || strings.ContainsAny(host, " \t\r\n,/@") {
		return false
	}
	if parsedHost, _, err := net.SplitHostPort(host); err == nil {
		host = parsedHost
	} else if strings.Contains(host, ":") && net.ParseIP(strings.Trim(host, "[]")) == nil {
		return false
	}
	host = strings.Trim(strings.TrimSpace(host), "[]")
	if strings.EqualFold(host, "localhost") {
		return true
	}
	ip := net.ParseIP(host)
	if ip != nil {
		return ip.IsLoopback()
	}
	return false
}

type GitHubOAuthEnvRuntimeOptions struct {
	LookupEnv      func(string) (string, bool)
	HTTPClient     GitHubOAuthHTTPClient
	IdentityBridge OAuthIdentityBridge
	Identity       *UnifiedIdentityService
	Now            func() time.Time
}

func NewGitHubOAuthServiceFromEnv(options GitHubOAuthEnvRuntimeOptions) (*GitHubOAuthService, error) {
	lookup := options.LookupEnv
	if lookup == nil {
		return nil, fmt.Errorf("GitHub OAuth environment lookup is required")
	}
	if !envBool(lookup, "RELEASEFOUNDRY_GITHUB_OAUTH_ENABLED") {
		return nil, nil
	}
	if !envBool(lookup, "RELEASEFOUNDRY_GITHUB_OAUTH_DEV_SESSION_ENABLED") {
		return nil, fmt.Errorf("GitHub OAuth requires an explicit session resolver; localhost dev session is disabled")
	}
	callbackURL := envValue(lookup, "RELEASEFOUNDRY_GITHUB_OAUTH_CALLBACK_URL")
	parsedCallback, err := parseLocalhostCallbackURL(callbackURL)
	if err != nil {
		return nil, err
	}
	store := NewMemoryGitHubOAuthStore()
	ttl := 10 * time.Minute
	if raw := envValue(lookup, "RELEASEFOUNDRY_GITHUB_OAUTH_TRANSACTION_TTL_SECONDS"); raw != "" {
		seconds, err := strconv.Atoi(raw)
		if err != nil || seconds < 30 || seconds > 3600 {
			return nil, fmt.Errorf("RELEASEFOUNDRY_GITHUB_OAUTH_TRANSACTION_TTL_SECONDS must be between 30 and 3600")
		}
		ttl = time.Duration(seconds) * time.Second
	}
	upstreamTimeout, err := oauthEnvDurationSeconds(lookup, "RELEASEFOUNDRY_GITHUB_OAUTH_UPSTREAM_TIMEOUT_SECONDS", 10*time.Second, 1, 60)
	if err != nil {
		return nil, err
	}
	fetchEmails := envBool(lookup, "RELEASEFOUNDRY_GITHUB_OAUTH_FETCH_EMAILS")
	scopes := []string{"read:user"}
	if fetchEmails {
		scopes = append(scopes, "user:email")
	}
	credentials := EnvGitHubOAuthCredentialsProvider{LookupEnv: lookup}
	if _, err := credentials.GitHubOAuthCredentials(context.Background()); err != nil {
		return nil, fmt.Errorf("GitHub OAuth credentials are unavailable")
	}
	authorizeURL := firstNonEmpty(envValue(lookup, "RELEASEFOUNDRY_GITHUB_OAUTH_AUTHORIZE_URL"), defaultGitHubAuthorizeURL)
	tokenURL := firstNonEmpty(envValue(lookup, "RELEASEFOUNDRY_GITHUB_OAUTH_TOKEN_URL"), defaultGitHubTokenURL)
	apiURL := firstNonEmpty(envValue(lookup, "RELEASEFOUNDRY_GITHUB_OAUTH_API_URL"), defaultGitHubAPIURL)
	for name, endpoint := range map[string]string{"authorize": authorizeURL, "token": tokenURL, "api": apiURL} {
		if err := validateGitHubOAuthEndpoint(name, endpoint); err != nil {
			return nil, err
		}
	}
	httpClient := options.HTTPClient
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 15 * time.Second}
	}
	var coordinator GitHubOAuthIdentityCoordinator
	if options.Identity != nil {
		coordinator, err = NewMemoryGitHubOAuthIdentityCoordinator(options.Identity, store)
		if err != nil {
			return nil, err
		}
	}
	return NewGitHubOAuthService(GitHubOAuthOptions{
		SessionResolver: LocalhostDevGitHubOAuthSessionResolver{
			Enabled:   true,
			TenantID:  envValue(lookup, "RELEASEFOUNDRY_GITHUB_OAUTH_DEV_TENANT_ID"),
			UserID:    envValue(lookup, "RELEASEFOUNDRY_GITHUB_OAUTH_DEV_USER_ID"),
			SessionID: envValue(lookup, "RELEASEFOUNDRY_GITHUB_OAUTH_DEV_SESSION_ID"),
			AccountID: envValue(lookup, "RELEASEFOUNDRY_GITHUB_OAUTH_DEV_ACCOUNT_ID"),
		},
		Credentials:         credentials,
		Transactions:        store,
		Secrets:             store,
		Connections:         store,
		IdentityBridge:      options.IdentityBridge,
		IdentityCoordinator: coordinator,
		HTTPClient:          httpClient,
		AuthorizeURL:        authorizeURL,
		TokenURL:            tokenURL,
		APIURL:              apiURL,
		CallbackURL:         parsedCallback.String(),
		Scopes:              scopes,
		FetchUserEmails:     fetchEmails,
		TransactionTTL:      ttl,
		UpstreamTimeout:     upstreamTimeout,
		Now:                 options.Now,
	})
}

func validateGitHubOAuthEndpoint(name, raw string) error {
	endpoint, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || endpoint.Scheme != "https" || endpoint.Host == "" || endpoint.User != nil || endpoint.Fragment != "" {
		return fmt.Errorf("GitHub OAuth %s endpoint must be an HTTPS URL", name)
	}
	return nil
}

func parseLocalhostCallbackURL(raw string) (*url.URL, error) {
	callback, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || callback.Scheme != "http" || callback.Host == "" {
		return nil, fmt.Errorf("GitHub OAuth callback URL must be an http localhost URL")
	}
	host := callback.Hostname()
	ip := net.ParseIP(host)
	if !strings.EqualFold(host, "localhost") && (ip == nil || !ip.IsLoopback()) {
		return nil, fmt.Errorf("GitHub OAuth callback URL must use localhost or a loopback IP")
	}
	if callback.Path != "/oauth/github/callback" {
		return nil, fmt.Errorf("GitHub OAuth callback URL path must be /oauth/github/callback")
	}
	return callback, nil
}

func envBool(lookup func(string) (string, bool), key string) bool {
	value, ok := lookup(key)
	if !ok {
		return false
	}
	parsed, err := strconv.ParseBool(strings.TrimSpace(value))
	return err == nil && parsed
}

func envValue(lookup func(string) (string, bool), key string) string {
	value, _ := lookup(key)
	return strings.TrimSpace(value)
}
