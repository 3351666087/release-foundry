package releasefoundry

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

const (
	GitHubOAuthSchemaVersion = "releasefoundry.github_oauth.v1"

	defaultGitHubAuthorizeURL = "https://github.com/login/oauth/authorize"
	defaultGitHubTokenURL     = "https://github.com/login/oauth/access_token"
	defaultGitHubAPIURL       = "https://api.github.com"
)

type GitHubOAuthSession struct {
	TenantID  string
	UserID    string
	SessionID string
	AccountID string
	Revoked   bool
}

type GitHubOAuthSessionResolver interface {
	ResolveGitHubOAuthSession(context.Context, *http.Request) (GitHubOAuthSession, error)
}

type GitHubOAuthCredentials struct {
	ClientID     string
	ClientSecret string
}

type GitHubOAuthCredentialsProvider interface {
	GitHubOAuthCredentials(context.Context) (GitHubOAuthCredentials, error)
}

type GitHubOAuthHTTPClient interface {
	Do(*http.Request) (*http.Response, error)
}

type GitHubOAuthTransaction struct {
	StateHash    string
	CodeVerifier string
	TenantID     string
	ProjectID    string
	SessionID    string
	UserID       string
	AccountID    string
	CreatedAt    time.Time
	ExpiresAt    time.Time
}

type GitHubOAuthTransactionStore interface {
	CreateGitHubOAuthTransaction(context.Context, GitHubOAuthTransaction) error
	ConsumeGitHubOAuthTransaction(context.Context, string, time.Time) (GitHubOAuthTransaction, error)
}

type GitHubOAuthSecretStore interface {
	PutGitHubOAuthToken(context.Context, GitHubOAuthSecretBinding, string) (string, error)
	GetGitHubOAuthToken(context.Context, string) (string, error)
	DeleteGitHubOAuthToken(context.Context, string) error
}

type GitHubOAuthSecretBinding struct {
	TenantID  string
	ProjectID string
	SessionID string
	UserID    string
	AccountID string
}

type GitHubOAuthConnection struct {
	SchemaVersion          string     `json:"schema_version"`
	TenantID               string     `json:"-"`
	ProjectID              string     `json:"-"`
	SessionID              string     `json:"-"`
	UserID                 string     `json:"-"`
	AccountID              string     `json:"account_id"`
	CredentialID           string     `json:"credential_id"`
	GitHubUserID           int64      `json:"-"`
	GitHubLogin            string     `json:"github_login"`
	ProviderSubjectHash    string     `json:"-"`
	ProviderSubjectPresent bool       `json:"provider_subject_present"`
	Email                  string     `json:"-"`
	EmailPresent           bool       `json:"email_present"`
	TokenRef               string     `json:"-"`
	ConnectedAt            time.Time  `json:"connected_at"`
	DisconnectedAt         *time.Time `json:"disconnected_at,omitempty"`
}

type GitHubOAuthConnectionStore interface {
	UpsertGitHubOAuthConnection(context.Context, GitHubOAuthConnection) (GitHubOAuthConnection, error)
	GetGitHubOAuthConnection(context.Context, GitHubOAuthSecretBinding) (GitHubOAuthConnection, error)
	DisconnectGitHubOAuthConnection(context.Context, GitHubOAuthSecretBinding, time.Time) (GitHubOAuthConnection, error)
}

type GitHubOAuthOptions struct {
	SessionResolver     GitHubOAuthSessionResolver
	Credentials         GitHubOAuthCredentialsProvider
	Transactions        GitHubOAuthTransactionStore
	Secrets             GitHubOAuthSecretStore
	Connections         GitHubOAuthConnectionStore
	IdentityBridge      OAuthIdentityBridge
	IdentityCoordinator GitHubOAuthIdentityCoordinator
	HTTPClient          GitHubOAuthHTTPClient
	AuthorizeURL        string
	TokenURL            string
	APIURL              string
	CallbackURL         string
	Scopes              []string
	FetchUserEmails     bool
	TransactionTTL      time.Duration
	UpstreamTimeout     time.Duration
	Now                 func() time.Time
	Random              io.Reader
}

type GitHubOAuthService struct {
	sessionResolver     GitHubOAuthSessionResolver
	credentials         GitHubOAuthCredentialsProvider
	transactions        GitHubOAuthTransactionStore
	secrets             GitHubOAuthSecretStore
	connections         GitHubOAuthConnectionStore
	identityBridge      OAuthIdentityBridge
	identityCoordinator GitHubOAuthIdentityCoordinator
	httpClient          GitHubOAuthHTTPClient
	authorizeURL        string
	tokenURL            string
	apiURL              string
	callbackURL         string
	scopes              []string
	fetchEmails         bool
	transactionTTL      time.Duration
	upstreamTimeout     time.Duration
	now                 func() time.Time
	random              io.Reader
}

type GitHubOAuthStartResult struct {
	SchemaVersion    string    `json:"schema_version"`
	Provider         string    `json:"provider"`
	AuthorizationURL string    `json:"authorize_url"`
	ExpiresAt        time.Time `json:"expires_at"`
}

type GitHubOAuthCallbackResult struct {
	SchemaVersion string                `json:"schema_version"`
	Provider      string                `json:"provider"`
	Connection    GitHubOAuthConnection `json:"connection"`
}

type GitHubOAuthDisconnectResult struct {
	SchemaVersion string                `json:"schema_version"`
	Provider      string                `json:"provider"`
	Disconnected  bool                  `json:"disconnected"`
	Connection    GitHubOAuthConnection `json:"connection"`
}

type GitHubOAuthError struct {
	Status  int
	Code    string
	Message string
	Cause   error
}

func (err GitHubOAuthError) Error() string {
	if err.Message != "" {
		return err.Message
	}
	return "GitHub OAuth request failed"
}

func (err GitHubOAuthError) Unwrap() error { return err.Cause }

var (
	ErrGitHubOAuthTransactionNotFound = errors.New("GitHub OAuth transaction not found")
	ErrGitHubOAuthTransactionExpired  = errors.New("GitHub OAuth transaction expired")
	ErrGitHubOAuthConnectionNotFound  = errors.New("GitHub OAuth connection not found")
)

func NewGitHubOAuthService(options GitHubOAuthOptions) (*GitHubOAuthService, error) {
	if options.SessionResolver == nil || options.Credentials == nil || options.Transactions == nil || options.Secrets == nil || options.Connections == nil {
		return nil, fmt.Errorf("GitHub OAuth session, credentials, transaction, secret, and connection stores are required")
	}
	if options.HTTPClient == nil {
		options.HTTPClient = &http.Client{Timeout: 15 * time.Second}
	}
	if options.TransactionTTL <= 0 {
		options.TransactionTTL = 10 * time.Minute
	}
	if options.UpstreamTimeout <= 0 {
		options.UpstreamTimeout = 10 * time.Second
	}
	if options.Now == nil {
		options.Now = time.Now
	}
	if options.Random == nil {
		options.Random = rand.Reader
	}
	if strings.TrimSpace(options.AuthorizeURL) == "" {
		options.AuthorizeURL = defaultGitHubAuthorizeURL
	}
	if strings.TrimSpace(options.TokenURL) == "" {
		options.TokenURL = defaultGitHubTokenURL
	}
	if strings.TrimSpace(options.APIURL) == "" {
		options.APIURL = defaultGitHubAPIURL
	}
	if strings.TrimSpace(options.CallbackURL) == "" {
		return nil, fmt.Errorf("GitHub OAuth callback URL is required")
	}
	scopes := sortedUniqueStrings(options.Scopes)
	if len(scopes) == 0 {
		scopes = []string{"read:user"}
	}
	if options.FetchUserEmails && !githubOAuthContainsString(scopes, "user:email") {
		scopes = append(scopes, "user:email")
	}
	if options.IdentityBridge == nil {
		identity, err := NewUnifiedIdentityService(UnifiedIdentityServiceOptions{})
		if err != nil {
			return nil, fmt.Errorf("initialize GitHub OAuth canonical identity: %w", err)
		}
		options.IdentityBridge = UnifiedIdentityOAuthBridge{Identity: identity}
	}
	return &GitHubOAuthService{
		sessionResolver:     options.SessionResolver,
		credentials:         options.Credentials,
		transactions:        options.Transactions,
		secrets:             options.Secrets,
		connections:         options.Connections,
		identityBridge:      options.IdentityBridge,
		identityCoordinator: options.IdentityCoordinator,
		httpClient:          options.HTTPClient,
		authorizeURL:        strings.TrimRight(options.AuthorizeURL, "/"),
		tokenURL:            strings.TrimRight(options.TokenURL, "/"),
		apiURL:              strings.TrimRight(options.APIURL, "/"),
		callbackURL:         options.CallbackURL,
		scopes:              scopes,
		fetchEmails:         options.FetchUserEmails,
		transactionTTL:      options.TransactionTTL,
		upstreamTimeout:     options.UpstreamTimeout,
		now:                 options.Now,
		random:              options.Random,
	}, nil
}

func (service *GitHubOAuthService) Start(ctx context.Context, request *http.Request, tenantID, projectID, accountID string) (GitHubOAuthStartResult, error) {
	session, err := service.resolveActiveSession(ctx, request, tenantID)
	if err != nil {
		return GitHubOAuthStartResult{}, err
	}
	accountID, err = canonicalOAuthAccountID(session.AccountID, accountID)
	if err != nil {
		return GitHubOAuthStartResult{}, githubOAuthErrorFromOAuthError(err)
	}
	if err := validateGitHubOAuthBinding(tenantID, projectID, accountID); err != nil {
		return GitHubOAuthStartResult{}, oauthPublicError(http.StatusBadRequest, "invalid_oauth_binding", err.Error(), err)
	}
	credentials, err := service.resolveCredentials(ctx)
	if err != nil {
		return GitHubOAuthStartResult{}, err
	}
	state, err := randomURLToken(service.random, 32)
	if err != nil {
		return GitHubOAuthStartResult{}, oauthInternalError("oauth_start_failed", err)
	}
	verifier, err := randomURLToken(service.random, 48)
	if err != nil {
		return GitHubOAuthStartResult{}, oauthInternalError("oauth_start_failed", err)
	}
	now := service.now().UTC()
	transaction := GitHubOAuthTransaction{
		StateHash: stateSHA256(state), CodeVerifier: verifier, TenantID: tenantID, ProjectID: projectID,
		SessionID: session.SessionID, UserID: session.UserID, AccountID: accountID, CreatedAt: now, ExpiresAt: now.Add(service.transactionTTL),
	}
	if err := service.transactions.CreateGitHubOAuthTransaction(ctx, transaction); err != nil {
		return GitHubOAuthStartResult{}, oauthInternalError("oauth_start_failed", err)
	}
	authorizeURL, err := url.Parse(service.authorizeURL)
	if err != nil {
		return GitHubOAuthStartResult{}, oauthInternalError("oauth_configuration_invalid", err)
	}
	query := authorizeURL.Query()
	query.Set("client_id", credentials.ClientID)
	query.Set("redirect_uri", service.callbackURL)
	query.Set("scope", strings.Join(service.scopes, " "))
	query.Set("state", state)
	query.Set("code_challenge", pkceS256(verifier))
	query.Set("code_challenge_method", "S256")
	authorizeURL.RawQuery = query.Encode()
	return GitHubOAuthStartResult{
		SchemaVersion: GitHubOAuthSchemaVersion, Provider: "github", AuthorizationURL: authorizeURL.String(), ExpiresAt: transaction.ExpiresAt,
	}, nil
}

func (service *GitHubOAuthService) Callback(ctx context.Context, request *http.Request, code, state string) (GitHubOAuthCallbackResult, error) {
	if strings.TrimSpace(code) == "" || strings.TrimSpace(state) == "" {
		return GitHubOAuthCallbackResult{}, oauthPublicError(http.StatusBadRequest, "invalid_oauth_callback", "code and state are required", nil)
	}
	transaction, err := service.transactions.ConsumeGitHubOAuthTransaction(ctx, stateSHA256(state), service.now().UTC())
	if err != nil {
		return GitHubOAuthCallbackResult{}, oauthPublicError(http.StatusBadRequest, "invalid_oauth_state", "OAuth state is invalid, expired, or already used", err)
	}
	session, err := service.resolveActiveSession(ctx, request, transaction.TenantID)
	if err != nil {
		return GitHubOAuthCallbackResult{}, err
	}
	if session.SessionID != transaction.SessionID || session.UserID != transaction.UserID {
		return GitHubOAuthCallbackResult{}, oauthPublicError(http.StatusForbidden, "oauth_binding_mismatch", "OAuth transaction does not match the authenticated session", nil)
	}
	if session.AccountID != "" && session.AccountID != transaction.AccountID {
		return GitHubOAuthCallbackResult{}, oauthPublicError(http.StatusForbidden, "account_mismatch", "OAuth transaction does not match the authenticated account", nil)
	}
	credentials, err := service.resolveCredentials(ctx)
	if err != nil {
		return GitHubOAuthCallbackResult{}, err
	}
	token, err := service.exchangeCode(ctx, credentials, code, transaction.CodeVerifier)
	if err != nil {
		return GitHubOAuthCallbackResult{}, err
	}
	user, err := service.fetchUser(ctx, token)
	if err != nil {
		return GitHubOAuthCallbackResult{}, err
	}
	email := ""
	if service.fetchEmails {
		email, err = service.fetchPrimaryEmail(ctx, token)
		if err != nil {
			return GitHubOAuthCallbackResult{}, err
		}
	}
	binding := GitHubOAuthSecretBinding{
		TenantID: transaction.TenantID, ProjectID: transaction.ProjectID, SessionID: transaction.SessionID,
		UserID: transaction.UserID, AccountID: transaction.AccountID,
	}
	tokenRef, err := service.secrets.PutGitHubOAuthToken(ctx, binding, token)
	if err != nil {
		return GitHubOAuthCallbackResult{}, oauthInternalError("oauth_secret_store_failed", err)
	}
	connection := GitHubOAuthConnection{
		SchemaVersion: GitHubOAuthSchemaVersion, TenantID: binding.TenantID, ProjectID: binding.ProjectID,
		SessionID: binding.SessionID, UserID: binding.UserID, AccountID: binding.AccountID,
		GitHubUserID: user.ID, GitHubLogin: user.Login,
		ProviderSubjectHash: githubProviderSubjectSHA256(user.ID), ProviderSubjectPresent: true,
		Email: email, EmailPresent: email != "", TokenRef: tokenRef, ConnectedAt: service.now().UTC(),
	}
	var stored GitHubOAuthConnection
	if service.identityCoordinator != nil {
		stored, err = service.identityCoordinator.CompleteCallback(ctx, CompleteGitHubOAuthCallbackCommand{
			AccountID: transaction.AccountID, ProviderSubject: githubOAuthProviderSubject(user.ID),
			ActorID: transaction.UserID, Connection: connection,
		})
	} else {
		var identityLink OAuthIdentityLinkResult
		identityLink, err = service.identityBridge.LinkVerifiedOAuthCredential(
			ctx, transaction.AccountID, "github", githubOAuthProviderSubject(user.ID), transaction.UserID,
		)
		if err == nil {
			connection.CredentialID = identityLink.Credential.CredentialID
			stored, err = service.connections.UpsertGitHubOAuthConnection(ctx, connection)
			if err != nil && identityLink.Created {
				_ = service.identityBridge.UnlinkOAuthCredential(
					context.Background(), transaction.AccountID, identityLink.Credential.CredentialID, transaction.UserID,
				)
			}
		}
	}
	if err != nil {
		_ = service.revokeToken(ctx, credentials, token)
		_ = service.secrets.DeleteGitHubOAuthToken(ctx, tokenRef)
		var githubError GitHubOAuthError
		if errors.As(err, &githubError) {
			return GitHubOAuthCallbackResult{}, githubError
		}
		var oauthError OAuthError
		if errors.As(err, &oauthError) {
			return GitHubOAuthCallbackResult{}, githubOAuthErrorFromOAuthError(oauthError)
		}
		return GitHubOAuthCallbackResult{}, oauthInternalError("oauth_connection_store_failed", err)
	}
	return GitHubOAuthCallbackResult{SchemaVersion: GitHubOAuthSchemaVersion, Provider: "github", Connection: stored}, nil
}

func (service *GitHubOAuthService) Disconnect(ctx context.Context, request *http.Request, tenantID, projectID, accountID string) (GitHubOAuthDisconnectResult, error) {
	session, err := service.resolveActiveSession(ctx, request, tenantID)
	if err != nil {
		return GitHubOAuthDisconnectResult{}, err
	}
	accountID, err = canonicalOAuthAccountID(session.AccountID, accountID)
	if err != nil {
		return GitHubOAuthDisconnectResult{}, githubOAuthErrorFromOAuthError(err)
	}
	if err := validateGitHubOAuthBinding(tenantID, projectID, accountID); err != nil {
		return GitHubOAuthDisconnectResult{}, oauthPublicError(http.StatusBadRequest, "invalid_oauth_binding", err.Error(), err)
	}
	binding := GitHubOAuthSecretBinding{TenantID: tenantID, ProjectID: projectID, SessionID: session.SessionID, UserID: session.UserID, AccountID: accountID}
	connection, err := service.connections.GetGitHubOAuthConnection(ctx, binding)
	if err != nil {
		return GitHubOAuthDisconnectResult{}, oauthPublicError(http.StatusNotFound, "oauth_connection_not_found", "GitHub connection not found", err)
	}
	if err := service.identityBridge.ValidateOAuthCredentialUnlink(ctx, accountID, connection.CredentialID); err != nil {
		return GitHubOAuthDisconnectResult{}, githubOAuthErrorFromOAuthError(err)
	}
	var token string
	if connection.TokenRef != "" {
		token, err = service.secrets.GetGitHubOAuthToken(ctx, connection.TokenRef)
		if err != nil || strings.TrimSpace(token) == "" {
			return GitHubOAuthDisconnectResult{}, oauthInternalError("oauth_secret_resolve_failed", err)
		}
		credentials, credentialsErr := service.resolveCredentials(ctx)
		if credentialsErr != nil {
			return GitHubOAuthDisconnectResult{}, credentialsErr
		}
		if revokeErr := service.revokeToken(ctx, credentials, token); revokeErr != nil {
			return GitHubOAuthDisconnectResult{}, revokeErr
		}
	}
	var disconnected GitHubOAuthConnection
	if service.identityCoordinator != nil {
		disconnected, err = service.identityCoordinator.DisconnectCredential(ctx, DisconnectGitHubOAuthCredentialCommand{
			AccountID: accountID, ActorID: session.UserID, Binding: binding, Disconnected: service.now().UTC(),
		})
	} else {
		disconnected, err = service.connections.DisconnectGitHubOAuthConnection(ctx, binding, service.now().UTC())
		if err == nil {
			err = service.identityBridge.UnlinkOAuthCredential(ctx, accountID, connection.CredentialID, session.UserID)
		}
	}
	if err != nil {
		return GitHubOAuthDisconnectResult{}, githubOAuthErrorFromOAuthError(err)
	}
	if connection.TokenRef != "" {
		if deleteErr := service.secrets.DeleteGitHubOAuthToken(ctx, connection.TokenRef); deleteErr != nil {
			return GitHubOAuthDisconnectResult{}, oauthInternalError("oauth_secret_delete_failed", deleteErr)
		}
	}
	return GitHubOAuthDisconnectResult{SchemaVersion: GitHubOAuthSchemaVersion, Provider: "github", Disconnected: true, Connection: disconnected}, nil
}

func (service *GitHubOAuthService) Connection(ctx context.Context, request *http.Request, tenantID, projectID, accountID string) (GitHubOAuthConnection, error) {
	session, err := service.resolveActiveSession(ctx, request, tenantID)
	if err != nil {
		return GitHubOAuthConnection{}, err
	}
	accountID, err = canonicalOAuthAccountID(session.AccountID, accountID)
	if err != nil {
		return GitHubOAuthConnection{}, githubOAuthErrorFromOAuthError(err)
	}
	if err := validateGitHubOAuthBinding(tenantID, projectID, accountID); err != nil {
		return GitHubOAuthConnection{}, oauthPublicError(http.StatusBadRequest, "invalid_oauth_binding", err.Error(), err)
	}
	binding := GitHubOAuthSecretBinding{
		TenantID: tenantID, ProjectID: projectID, SessionID: session.SessionID,
		UserID: session.UserID, AccountID: accountID,
	}
	connection, err := service.connections.GetGitHubOAuthConnection(ctx, binding)
	if err != nil {
		return GitHubOAuthConnection{}, oauthPublicError(http.StatusNotFound, "oauth_connection_not_found", "GitHub connection not found", err)
	}
	return connection, nil
}

func (service *GitHubOAuthService) resolveActiveSession(ctx context.Context, request *http.Request, tenantID string) (GitHubOAuthSession, error) {
	session, err := service.sessionResolver.ResolveGitHubOAuthSession(ctx, request)
	if err != nil || session.Revoked || strings.TrimSpace(session.SessionID) == "" || strings.TrimSpace(session.UserID) == "" {
		return GitHubOAuthSession{}, oauthPublicError(http.StatusUnauthorized, "session_invalid", "an active authenticated session is required", err)
	}
	if strings.TrimSpace(session.TenantID) == "" || session.TenantID != tenantID {
		return GitHubOAuthSession{}, oauthPublicError(http.StatusForbidden, "tenant_mismatch", "tenant does not match the authenticated session", nil)
	}
	return session, nil
}

func githubOAuthErrorFromOAuthError(err error) GitHubOAuthError {
	var oauthError OAuthError
	if errors.As(err, &oauthError) {
		return GitHubOAuthError{
			Status: oauthError.Status, Code: oauthError.Code, Message: oauthError.Message, Cause: oauthError.Cause,
		}
	}
	return GitHubOAuthError{
		Status: http.StatusInternalServerError, Code: "github_oauth_failed",
		Message: "GitHub OAuth request could not be completed", Cause: err,
	}
}

func (service *GitHubOAuthService) resolveCredentials(ctx context.Context) (GitHubOAuthCredentials, error) {
	credentials, err := service.credentials.GitHubOAuthCredentials(ctx)
	if err != nil || strings.TrimSpace(credentials.ClientID) == "" || strings.TrimSpace(credentials.ClientSecret) == "" {
		return GitHubOAuthCredentials{}, oauthInternalError("oauth_credentials_unavailable", err)
	}
	return credentials, nil
}

func (service *GitHubOAuthService) exchangeCode(ctx context.Context, credentials GitHubOAuthCredentials, code, verifier string) (string, error) {
	form := url.Values{
		"client_id": {credentials.ClientID}, "client_secret": {credentials.ClientSecret}, "code": {code},
		"redirect_uri": {service.callbackURL}, "code_verifier": {verifier},
	}
	request, cancel, err := service.newUpstreamRequest(ctx, http.MethodPost, service.tokenURL, strings.NewReader(form.Encode()))
	if err != nil {
		return "", oauthInternalError("github_token_exchange_failed", err)
	}
	defer cancel()
	request.Header.Set("Accept", "application/json")
	request.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	response, err := service.httpClient.Do(request)
	if err != nil {
		return "", oauthPublicError(http.StatusBadGateway, "github_token_exchange_failed", "GitHub token exchange failed", err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, 1<<20))
	if err != nil {
		return "", oauthPublicError(http.StatusBadGateway, "github_token_exchange_failed", "GitHub token exchange failed", err)
	}
	var payload struct {
		AccessToken string `json:"access_token"`
		TokenType   string `json:"token_type"`
		Scope       string `json:"scope"`
		Error       string `json:"error"`
	}
	if err := json.Unmarshal(body, &payload); err != nil || response.StatusCode < 200 || response.StatusCode >= 300 || payload.Error != "" || strings.TrimSpace(payload.AccessToken) == "" {
		return "", oauthPublicError(http.StatusBadGateway, "github_token_exchange_failed", "GitHub token exchange failed", nil)
	}
	if !strings.EqualFold(strings.TrimSpace(payload.TokenType), "bearer") {
		return "", oauthPublicError(http.StatusBadGateway, "github_token_exchange_failed", "GitHub token exchange failed", nil)
	}
	grantedScopes := githubOAuthParseScopes(payload.Scope)
	for _, granted := range grantedScopes {
		if !githubOAuthContainsString(service.scopes, granted) {
			return "", oauthPublicError(http.StatusBadGateway, "github_scope_escalation", "GitHub granted an unexpected OAuth scope", nil)
		}
	}
	if len(grantedScopes) != len(service.scopes) {
		return "", oauthPublicError(http.StatusBadGateway, "github_scope_mismatch", "GitHub granted a different OAuth scope set than requested", nil)
	}
	for _, requested := range service.scopes {
		if !githubOAuthContainsString(grantedScopes, requested) {
			return "", oauthPublicError(http.StatusBadGateway, "github_scope_mismatch", "GitHub did not grant every requested OAuth scope", nil)
		}
	}
	return payload.AccessToken, nil
}

func githubOAuthParseScopes(value string) []string {
	seen := map[string]struct{}{}
	scopes := make([]string, 0)
	for _, candidate := range strings.Split(value, ",") {
		scope := strings.TrimSpace(candidate)
		if scope == "" {
			continue
		}
		if _, exists := seen[scope]; exists {
			continue
		}
		seen[scope] = struct{}{}
		scopes = append(scopes, scope)
	}
	return scopes
}

func (service *GitHubOAuthService) revokeToken(ctx context.Context, credentials GitHubOAuthCredentials, token string) error {
	payload, err := json.Marshal(map[string]string{"access_token": token})
	if err != nil {
		return oauthInternalError("github_token_revoke_failed", err)
	}
	endpoint := fmt.Sprintf("%s/applications/%s/token", service.apiURL, url.PathEscape(credentials.ClientID))
	request, cancel, err := service.newUpstreamRequest(ctx, http.MethodDelete, endpoint, strings.NewReader(string(payload)))
	if err != nil {
		return oauthInternalError("github_token_revoke_failed", err)
	}
	defer cancel()
	request.SetBasicAuth(credentials.ClientID, credentials.ClientSecret)
	request.Header.Set("Accept", "application/vnd.github+json")
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-GitHub-Api-Version", "2022-11-28")
	response, err := service.httpClient.Do(request)
	if err != nil {
		return oauthPublicError(http.StatusBadGateway, "github_token_revoke_failed", "GitHub token revocation failed; the local connection was retained", err)
	}
	defer response.Body.Close()
	_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 1<<20))
	if response.StatusCode != http.StatusNoContent {
		return oauthPublicError(http.StatusBadGateway, "github_token_revoke_failed", "GitHub token revocation failed; the local connection was retained", nil)
	}
	return nil
}

type githubOAuthUser struct {
	ID    int64  `json:"id"`
	Login string `json:"login"`
	Email string `json:"email"`
}

func (service *GitHubOAuthService) fetchUser(ctx context.Context, token string) (githubOAuthUser, error) {
	var user githubOAuthUser
	if err := service.githubAPIGet(ctx, token, "/user", &user); err != nil {
		return githubOAuthUser{}, err
	}
	if user.ID <= 0 || strings.TrimSpace(user.Login) == "" {
		return githubOAuthUser{}, oauthPublicError(http.StatusBadGateway, "github_user_lookup_failed", "GitHub user lookup returned an invalid identity", nil)
	}
	return user, nil
}

func (service *GitHubOAuthService) fetchPrimaryEmail(ctx context.Context, token string) (string, error) {
	var emails []struct {
		Email    string `json:"email"`
		Primary  bool   `json:"primary"`
		Verified bool   `json:"verified"`
	}
	if err := service.githubAPIGet(ctx, token, "/user/emails", &emails); err != nil {
		return "", err
	}
	for _, email := range emails {
		if email.Primary && email.Verified {
			return strings.TrimSpace(email.Email), nil
		}
	}
	return "", nil
}

func (service *GitHubOAuthService) githubAPIGet(ctx context.Context, token, path string, destination any) error {
	request, cancel, err := service.newUpstreamRequest(ctx, http.MethodGet, service.apiURL+path, nil)
	if err != nil {
		return oauthInternalError("github_user_lookup_failed", err)
	}
	defer cancel()
	request.Header.Set("Accept", "application/vnd.github+json")
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("X-GitHub-Api-Version", "2022-11-28")
	response, err := service.httpClient.Do(request)
	if err != nil {
		return oauthPublicError(http.StatusBadGateway, "github_user_lookup_failed", "GitHub user lookup failed", err)
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 1<<20))
		return oauthPublicError(http.StatusBadGateway, "github_user_lookup_failed", "GitHub user lookup failed", nil)
	}
	if err := json.NewDecoder(io.LimitReader(response.Body, 1<<20)).Decode(destination); err != nil {
		return oauthPublicError(http.StatusBadGateway, "github_user_lookup_failed", "GitHub user lookup failed", err)
	}
	return nil
}

func oauthPublicError(status int, code, message string, cause error) GitHubOAuthError {
	return GitHubOAuthError{Status: status, Code: code, Message: message, Cause: cause}
}

func oauthInternalError(code string, cause error) GitHubOAuthError {
	return GitHubOAuthError{Status: http.StatusInternalServerError, Code: code, Message: "GitHub OAuth request could not be completed", Cause: cause}
}

func validateGitHubOAuthBinding(tenantID, projectID, accountID string) error {
	for name, value := range map[string]string{"tenant_id": tenantID, "project_id": projectID, "account_id": accountID} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("%s is required", name)
		}
	}
	return nil
}

func randomURLToken(reader io.Reader, size int) (string, error) {
	value := make([]byte, size)
	if _, err := io.ReadFull(reader, value); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(value), nil
}

func stateSHA256(state string) string {
	sum := sha256.Sum256([]byte(state))
	return base64.RawURLEncoding.EncodeToString(sum[:])
}

func pkceS256(verifier string) string {
	sum := sha256.Sum256([]byte(verifier))
	return base64.RawURLEncoding.EncodeToString(sum[:])
}

func githubProviderSubjectSHA256(userID int64) string {
	sum := sha256.Sum256([]byte(fmt.Sprintf("github:%d", userID)))
	return fmt.Sprintf("%x", sum[:])
}

func githubOAuthContainsString(values []string, candidate string) bool {
	for _, value := range values {
		if value == candidate {
			return true
		}
	}
	return false
}

func (service *GitHubOAuthService) newUpstreamRequest(ctx context.Context, method, endpoint string, body io.Reader) (*http.Request, context.CancelFunc, error) {
	upstreamContext, cancel := context.WithTimeout(ctx, service.upstreamTimeout)
	request, err := http.NewRequestWithContext(upstreamContext, method, endpoint, body)
	if err != nil {
		cancel()
		return nil, func() {}, err
	}
	return request, cancel, nil
}

type MemoryGitHubOAuthStore struct {
	mu            sync.Mutex
	transactions  map[string]GitHubOAuthTransaction
	secrets       map[string]string
	connections   map[string]GitHubOAuthConnection
	subjectOwners map[string]string
	random        io.Reader
}

func NewMemoryGitHubOAuthStore() *MemoryGitHubOAuthStore {
	return &MemoryGitHubOAuthStore{
		transactions:  map[string]GitHubOAuthTransaction{},
		secrets:       map[string]string{},
		connections:   map[string]GitHubOAuthConnection{},
		subjectOwners: map[string]string{},
		random:        rand.Reader,
	}
}

func (store *MemoryGitHubOAuthStore) CreateGitHubOAuthTransaction(_ context.Context, transaction GitHubOAuthTransaction) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if _, exists := store.transactions[transaction.StateHash]; exists {
		return fmt.Errorf("OAuth state collision")
	}
	store.transactions[transaction.StateHash] = transaction
	return nil
}

func (store *MemoryGitHubOAuthStore) ConsumeGitHubOAuthTransaction(_ context.Context, stateHash string, now time.Time) (GitHubOAuthTransaction, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	transaction, exists := store.transactions[stateHash]
	if !exists {
		return GitHubOAuthTransaction{}, ErrGitHubOAuthTransactionNotFound
	}
	delete(store.transactions, stateHash)
	if !now.Before(transaction.ExpiresAt) {
		return GitHubOAuthTransaction{}, ErrGitHubOAuthTransactionExpired
	}
	return transaction, nil
}

func (store *MemoryGitHubOAuthStore) PutGitHubOAuthToken(_ context.Context, binding GitHubOAuthSecretBinding, token string) (string, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	refToken, err := randomURLToken(store.random, 24)
	if err != nil {
		return "", err
	}
	ref := "github_oauth_ref_" + refToken
	store.secrets[ref] = token
	return ref, nil
}

func (store *MemoryGitHubOAuthStore) DeleteGitHubOAuthToken(_ context.Context, ref string) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	delete(store.secrets, ref)
	return nil
}

func (store *MemoryGitHubOAuthStore) GetGitHubOAuthToken(_ context.Context, ref string) (string, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	token, exists := store.secrets[ref]
	if !exists {
		return "", fmt.Errorf("GitHub OAuth token reference was not found")
	}
	return token, nil
}

func (store *MemoryGitHubOAuthStore) UpsertGitHubOAuthConnection(_ context.Context, connection GitHubOAuthConnection) (GitHubOAuthConnection, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	subjectKey := "github:" + strings.ToLower(strings.TrimSpace(connection.ProviderSubjectHash))
	if owner, exists := store.subjectOwners[subjectKey]; exists && owner != connection.AccountID {
		return GitHubOAuthConnection{}, GitHubOAuthError{
			Status: http.StatusConflict, Code: "credential_link_conflict",
			Message: "verified provider credential is already linked to another account",
		}
	}
	key := githubOAuthBindingKey(GitHubOAuthSecretBinding{
		TenantID: connection.TenantID, ProjectID: connection.ProjectID, SessionID: connection.SessionID,
		UserID: connection.UserID, AccountID: connection.AccountID,
	})
	if previous, exists := store.connections[key]; exists && previous.TokenRef != "" && previous.TokenRef != connection.TokenRef {
		delete(store.secrets, previous.TokenRef)
	}
	store.subjectOwners[subjectKey] = connection.AccountID
	store.connections[key] = connection
	return connection, nil
}

func (store *MemoryGitHubOAuthStore) GetGitHubOAuthConnection(_ context.Context, binding GitHubOAuthSecretBinding) (GitHubOAuthConnection, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	connection, exists := store.connections[githubOAuthBindingKey(binding)]
	if !exists || connection.DisconnectedAt != nil {
		return GitHubOAuthConnection{}, ErrGitHubOAuthConnectionNotFound
	}
	return connection, nil
}

func (store *MemoryGitHubOAuthStore) DisconnectGitHubOAuthConnection(_ context.Context, binding GitHubOAuthSecretBinding, at time.Time) (GitHubOAuthConnection, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	key := githubOAuthBindingKey(binding)
	connection, exists := store.connections[key]
	if !exists || connection.DisconnectedAt != nil {
		return GitHubOAuthConnection{}, ErrGitHubOAuthConnectionNotFound
	}
	connection.TokenRef = ""
	connection.DisconnectedAt = &at
	store.connections[key] = connection
	return connection, nil
}

func githubOAuthBindingKey(binding GitHubOAuthSecretBinding) string {
	return strings.Join([]string{binding.TenantID, binding.ProjectID, binding.SessionID, binding.UserID, binding.AccountID}, "\x00")
}
