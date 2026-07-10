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

type EnvGitHubOAuthCredentialsProvider struct {
	LookupEnv func(string) (string, bool)
}

func (provider EnvGitHubOAuthCredentialsProvider) GitHubOAuthCredentials(context.Context) (GitHubOAuthCredentials, error) {
	lookup := provider.LookupEnv
	if lookup == nil {
		return GitHubOAuthCredentials{}, fmt.Errorf("GitHub OAuth environment lookup is not configured")
	}
	clientID, clientIDOK := lookup("ASHR_GITHUB_OAUTH_CLIENT_ID")
	clientSecret, clientSecretOK := lookup("ASHR_GITHUB_OAUTH_CLIENT_SECRET")
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
	}
	if session.TenantID == "" || session.UserID == "" || session.SessionID == "" {
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
		strings.TrimSpace(request.Header.Get("X-Forwarded-Host")) != "" {
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
	host := request.Host
	if parsedHost, _, err := net.SplitHostPort(host); err == nil {
		host = parsedHost
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
	LookupEnv  func(string) (string, bool)
	HTTPClient GitHubOAuthHTTPClient
	Now        func() time.Time
}

func NewGitHubOAuthServiceFromEnv(options GitHubOAuthEnvRuntimeOptions) (*GitHubOAuthService, error) {
	lookup := options.LookupEnv
	if lookup == nil {
		return nil, fmt.Errorf("GitHub OAuth environment lookup is required")
	}
	if !envBool(lookup, "ASHR_GITHUB_OAUTH_ENABLED") {
		return nil, nil
	}
	if !envBool(lookup, "ASHR_GITHUB_OAUTH_DEV_SESSION_ENABLED") {
		return nil, fmt.Errorf("GitHub OAuth requires an explicit session resolver; localhost dev session is disabled")
	}
	callbackURL := envValue(lookup, "ASHR_GITHUB_OAUTH_CALLBACK_URL")
	parsedCallback, err := parseLocalhostCallbackURL(callbackURL)
	if err != nil {
		return nil, err
	}
	store := NewMemoryGitHubOAuthStore()
	ttl := 10 * time.Minute
	if raw := envValue(lookup, "ASHR_GITHUB_OAUTH_TRANSACTION_TTL_SECONDS"); raw != "" {
		seconds, err := strconv.Atoi(raw)
		if err != nil || seconds < 30 || seconds > 3600 {
			return nil, fmt.Errorf("ASHR_GITHUB_OAUTH_TRANSACTION_TTL_SECONDS must be between 30 and 3600")
		}
		ttl = time.Duration(seconds) * time.Second
	}
	fetchEmails := envBool(lookup, "ASHR_GITHUB_OAUTH_FETCH_EMAILS")
	scopes := []string{"read:user"}
	if fetchEmails {
		scopes = append(scopes, "user:email")
	}
	credentials := EnvGitHubOAuthCredentialsProvider{LookupEnv: lookup}
	if _, err := credentials.GitHubOAuthCredentials(context.Background()); err != nil {
		return nil, fmt.Errorf("GitHub OAuth credentials are unavailable")
	}
	authorizeURL := firstNonEmpty(envValue(lookup, "ASHR_GITHUB_OAUTH_AUTHORIZE_URL"), defaultGitHubAuthorizeURL)
	tokenURL := firstNonEmpty(envValue(lookup, "ASHR_GITHUB_OAUTH_TOKEN_URL"), defaultGitHubTokenURL)
	apiURL := firstNonEmpty(envValue(lookup, "ASHR_GITHUB_OAUTH_API_URL"), defaultGitHubAPIURL)
	for name, endpoint := range map[string]string{"authorize": authorizeURL, "token": tokenURL, "api": apiURL} {
		if err := validateGitHubOAuthEndpoint(name, endpoint); err != nil {
			return nil, err
		}
	}
	httpClient := options.HTTPClient
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 15 * time.Second}
	}
	return NewGitHubOAuthService(GitHubOAuthOptions{
		SessionResolver: LocalhostDevGitHubOAuthSessionResolver{
			Enabled:   true,
			TenantID:  envValue(lookup, "ASHR_GITHUB_OAUTH_DEV_TENANT_ID"),
			UserID:    envValue(lookup, "ASHR_GITHUB_OAUTH_DEV_USER_ID"),
			SessionID: envValue(lookup, "ASHR_GITHUB_OAUTH_DEV_SESSION_ID"),
		},
		Credentials:     credentials,
		Transactions:    store,
		Secrets:         store,
		Connections:     store,
		HTTPClient:      httpClient,
		AuthorizeURL:    authorizeURL,
		TokenURL:        tokenURL,
		APIURL:          apiURL,
		CallbackURL:     parsedCallback.String(),
		Scopes:          scopes,
		FetchUserEmails: fetchEmails,
		TransactionTTL:  ttl,
		Now:             options.Now,
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
