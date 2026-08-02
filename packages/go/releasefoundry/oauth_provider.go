package releasefoundry

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"sort"
	"strings"
	"sync"
	"time"
)

const OAuthConnectionSchemaVersion = "releasefoundry.oauth_connection.v1"

var (
	ErrOAuthTransactionNotFound = errors.New("OAuth transaction not found")
	ErrOAuthTransactionExpired  = errors.New("OAuth transaction expired")
	ErrOAuthConnectionNotFound  = errors.New("OAuth connection not found")
)

type OAuthSession struct {
	TenantID  string
	UserID    string
	SessionID string
	AccountID string
	Revoked   bool
}

type OAuthSessionResolver interface {
	ResolveOAuthSession(context.Context, *http.Request) (OAuthSession, error)
}

type OAuthClientCredentials struct {
	ClientID     string
	ClientSecret string
}

type OAuthCredentialsProvider interface {
	OAuthCredentials(context.Context, string) (OAuthClientCredentials, error)
}

type OAuthHTTPClient interface {
	Do(*http.Request) (*http.Response, error)
}

type OAuthAuthorizationRequest struct {
	ClientID      string
	CallbackURL   string
	State         string
	CodeChallenge string
	Nonce         string
	Scopes        []string
}

type OAuthCodeExchangeRequest struct {
	Credentials  OAuthClientCredentials
	CallbackURL  string
	Code         string
	CodeVerifier string
}

type OAuthTokenSet struct {
	AccessToken string
	TokenType   string
	Scopes      []string
	IDToken     string
}

type OAuthIdentityRequest struct {
	TokenSet OAuthTokenSet
	Nonce    string
	ClientID string
	Now      time.Time
}

type OAuthProviderIdentity struct {
	Subject       string
	DisplayName   string
	Email         string
	EmailVerified bool
}

type OAuthProviderAdapter interface {
	Name() string
	SchemaVersion() string
	ExactScopes() []string
	AuthorizationURL(OAuthAuthorizationRequest) (string, error)
	ExchangeCode(context.Context, OAuthCodeExchangeRequest) (OAuthTokenSet, error)
	ResolveIdentity(context.Context, OAuthIdentityRequest) (OAuthProviderIdentity, error)
	RevokeToken(context.Context, OAuthClientCredentials, string) error
}

type OAuthTransaction struct {
	Provider     string
	StateHash    string
	CodeVerifier string
	Nonce        string
	TenantID     string
	ProjectID    string
	SessionID    string
	UserID       string
	AccountID    string
	CreatedAt    time.Time
	ExpiresAt    time.Time
}

type OAuthTransactionStore interface {
	CreateOAuthTransaction(context.Context, OAuthTransaction) error
	ConsumeOAuthTransaction(context.Context, string, string, time.Time) (OAuthTransaction, error)
}

type OAuthSecretBinding struct {
	Provider  string
	TenantID  string
	ProjectID string
	SessionID string
	UserID    string
	AccountID string
}

type OAuthSecretStore interface {
	PutOAuthToken(context.Context, OAuthSecretBinding, string) (string, error)
	GetOAuthToken(context.Context, string) (string, error)
	DeleteOAuthToken(context.Context, string) error
}

type OAuthConnection struct {
	SchemaVersion          string     `json:"schema_version"`
	Provider               string     `json:"provider"`
	TenantID               string     `json:"-"`
	ProjectID              string     `json:"-"`
	SessionID              string     `json:"-"`
	UserID                 string     `json:"-"`
	AccountID              string     `json:"account_id"`
	CredentialID           string     `json:"credential_id"`
	ProviderSubjectHash    string     `json:"-"`
	ProviderSubjectPresent bool       `json:"provider_subject_present"`
	DisplayName            string     `json:"display_name,omitempty"`
	Email                  string     `json:"-"`
	EmailPresent           bool       `json:"email_present"`
	EmailVerified          bool       `json:"email_verified"`
	TokenRef               string     `json:"-"`
	ConnectedAt            time.Time  `json:"connected_at"`
	DisconnectedAt         *time.Time `json:"disconnected_at,omitempty"`
}

type OAuthConnectionStore interface {
	UpsertOAuthConnection(context.Context, OAuthConnection) (OAuthConnection, error)
	GetOAuthConnection(context.Context, OAuthSecretBinding) (OAuthConnection, error)
	DisconnectOAuthConnection(context.Context, OAuthSecretBinding, time.Time) (OAuthConnection, error)
}

type OAuthServiceOptions struct {
	Provider            OAuthProviderAdapter
	SessionResolver     OAuthSessionResolver
	Credentials         OAuthCredentialsProvider
	Transactions        OAuthTransactionStore
	Secrets             OAuthSecretStore
	Connections         OAuthConnectionStore
	IdentityBridge      OAuthIdentityBridge
	IdentityCoordinator OAuthIdentityCoordinator
	CallbackURL         string
	TransactionTTL      time.Duration
	Now                 func() time.Time
	Random              io.Reader
}

type OAuthService struct {
	provider            OAuthProviderAdapter
	sessionResolver     OAuthSessionResolver
	credentials         OAuthCredentialsProvider
	transactions        OAuthTransactionStore
	secrets             OAuthSecretStore
	connections         OAuthConnectionStore
	identityBridge      OAuthIdentityBridge
	identityCoordinator OAuthIdentityCoordinator
	callbackURL         string
	transactionTTL      time.Duration
	now                 func() time.Time
	random              io.Reader
}

type OAuthStartResult struct {
	SchemaVersion    string    `json:"schema_version"`
	Provider         string    `json:"provider"`
	AuthorizationURL string    `json:"authorize_url"`
	ExpiresAt        time.Time `json:"expires_at"`
}

type OAuthCallbackResult struct {
	SchemaVersion string          `json:"schema_version"`
	Provider      string          `json:"provider"`
	Connection    OAuthConnection `json:"connection"`
}

type OAuthDisconnectResult struct {
	SchemaVersion string          `json:"schema_version"`
	Provider      string          `json:"provider"`
	Disconnected  bool            `json:"disconnected"`
	Connection    OAuthConnection `json:"connection"`
}

type OAuthError struct {
	Status  int
	Code    string
	Message string
	Cause   error
}

func (err OAuthError) Error() string {
	if err.Message != "" {
		return err.Message
	}
	return "OAuth request failed"
}

func (err OAuthError) Unwrap() error { return err.Cause }

func NewOAuthService(options OAuthServiceOptions) (*OAuthService, error) {
	if options.Provider == nil || options.SessionResolver == nil || options.Credentials == nil ||
		options.Transactions == nil || options.Secrets == nil || options.Connections == nil {
		return nil, fmt.Errorf("OAuth provider, session, credentials, transaction, secret, and connection stores are required")
	}
	if strings.TrimSpace(options.CallbackURL) == "" {
		return nil, fmt.Errorf("OAuth callback URL is required")
	}
	if options.TransactionTTL <= 0 {
		options.TransactionTTL = 10 * time.Minute
	}
	if options.Now == nil {
		options.Now = time.Now
	}
	if options.Random == nil {
		options.Random = rand.Reader
	}
	if err := validateExactOAuthScopes(options.Provider.ExactScopes()); err != nil {
		return nil, fmt.Errorf("%s OAuth scopes: %w", options.Provider.Name(), err)
	}
	if options.IdentityBridge == nil {
		identity, err := NewUnifiedIdentityService(UnifiedIdentityServiceOptions{})
		if err != nil {
			return nil, fmt.Errorf("initialize OAuth canonical identity: %w", err)
		}
		options.IdentityBridge = UnifiedIdentityOAuthBridge{Identity: identity}
	}
	return &OAuthService{
		provider: options.Provider, sessionResolver: options.SessionResolver, credentials: options.Credentials,
		transactions: options.Transactions, secrets: options.Secrets, connections: options.Connections,
		identityBridge:      options.IdentityBridge,
		identityCoordinator: options.IdentityCoordinator,
		callbackURL:         options.CallbackURL, transactionTTL: options.TransactionTTL, now: options.Now, random: options.Random,
	}, nil
}

func (service *OAuthService) ProviderName() string {
	if service == nil || service.provider == nil {
		return ""
	}
	return strings.ToLower(strings.TrimSpace(service.provider.Name()))
}

func (service *OAuthService) Start(ctx context.Context, request *http.Request, tenantID, projectID, accountID string) (OAuthStartResult, error) {
	session, err := service.resolveActiveSession(ctx, request, tenantID)
	if err != nil {
		return OAuthStartResult{}, err
	}
	accountID, err = canonicalOAuthAccountID(session.AccountID, accountID)
	if err != nil {
		return OAuthStartResult{}, err
	}
	if err := validateOAuthBinding(tenantID, projectID, accountID); err != nil {
		return OAuthStartResult{}, newOAuthPublicError(http.StatusBadRequest, "invalid_oauth_binding", err.Error(), err)
	}
	credentials, err := service.resolveCredentials(ctx)
	if err != nil {
		return OAuthStartResult{}, err
	}
	state, err := randomURLToken(service.random, 32)
	if err != nil {
		return OAuthStartResult{}, service.internalError("oauth_start_failed", err)
	}
	verifier, err := randomURLToken(service.random, 48)
	if err != nil {
		return OAuthStartResult{}, service.internalError("oauth_start_failed", err)
	}
	nonce, err := randomURLToken(service.random, 32)
	if err != nil {
		return OAuthStartResult{}, service.internalError("oauth_start_failed", err)
	}
	now := service.now().UTC()
	transaction := OAuthTransaction{
		Provider: service.provider.Name(), StateHash: stateSHA256(state), CodeVerifier: verifier, Nonce: nonce,
		TenantID: tenantID, ProjectID: projectID, SessionID: session.SessionID, UserID: session.UserID,
		AccountID: accountID, CreatedAt: now, ExpiresAt: now.Add(service.transactionTTL),
	}
	if err := service.transactions.CreateOAuthTransaction(ctx, transaction); err != nil {
		return OAuthStartResult{}, service.internalError("oauth_start_failed", err)
	}
	authorizationURL, err := service.provider.AuthorizationURL(OAuthAuthorizationRequest{
		ClientID: credentials.ClientID, CallbackURL: service.callbackURL, State: state,
		CodeChallenge: pkceS256(verifier), Nonce: nonce, Scopes: service.provider.ExactScopes(),
	})
	if err != nil {
		return OAuthStartResult{}, service.internalError("oauth_configuration_invalid", err)
	}
	return OAuthStartResult{
		SchemaVersion: service.provider.SchemaVersion(), Provider: service.provider.Name(),
		AuthorizationURL: authorizationURL, ExpiresAt: transaction.ExpiresAt,
	}, nil
}

func (service *OAuthService) Callback(ctx context.Context, request *http.Request, code, state string) (OAuthCallbackResult, error) {
	if strings.TrimSpace(code) == "" || strings.TrimSpace(state) == "" {
		return OAuthCallbackResult{}, newOAuthPublicError(http.StatusBadRequest, "invalid_oauth_callback", "code and state are required", nil)
	}
	transaction, err := service.transactions.ConsumeOAuthTransaction(ctx, service.provider.Name(), stateSHA256(state), service.now().UTC())
	if err != nil {
		return OAuthCallbackResult{}, newOAuthPublicError(http.StatusBadRequest, "invalid_oauth_state", "OAuth state is invalid, expired, or already used", err)
	}
	session, err := service.resolveActiveSession(ctx, request, transaction.TenantID)
	if err != nil {
		return OAuthCallbackResult{}, err
	}
	if session.SessionID != transaction.SessionID || session.UserID != transaction.UserID {
		return OAuthCallbackResult{}, newOAuthPublicError(http.StatusForbidden, "oauth_binding_mismatch", "OAuth transaction does not match the authenticated session", nil)
	}
	if session.AccountID != "" && session.AccountID != transaction.AccountID {
		return OAuthCallbackResult{}, newOAuthPublicError(http.StatusForbidden, "account_mismatch", "OAuth transaction does not match the authenticated account", nil)
	}
	credentials, err := service.resolveCredentials(ctx)
	if err != nil {
		return OAuthCallbackResult{}, err
	}
	tokenSet, err := service.provider.ExchangeCode(ctx, OAuthCodeExchangeRequest{
		Credentials: credentials, CallbackURL: service.callbackURL, Code: code, CodeVerifier: transaction.CodeVerifier,
	})
	if err != nil {
		return OAuthCallbackResult{}, err
	}
	if err := requireExactOAuthScopes(service.provider.ExactScopes(), tokenSet.Scopes); err != nil {
		return OAuthCallbackResult{}, newOAuthPublicError(http.StatusBadGateway, "oauth_scope_mismatch", "provider granted a different OAuth scope set than requested", err)
	}
	identity, err := service.provider.ResolveIdentity(ctx, OAuthIdentityRequest{
		TokenSet: tokenSet, Nonce: transaction.Nonce, ClientID: credentials.ClientID, Now: service.now().UTC(),
	})
	if err != nil {
		return OAuthCallbackResult{}, err
	}
	if strings.TrimSpace(identity.Subject) == "" || (identity.Email != "" && !identity.EmailVerified) {
		return OAuthCallbackResult{}, newOAuthPublicError(http.StatusBadGateway, "oauth_identity_invalid", "provider returned an invalid identity", nil)
	}
	binding := OAuthSecretBinding{
		Provider: service.provider.Name(), TenantID: transaction.TenantID, ProjectID: transaction.ProjectID,
		SessionID: transaction.SessionID, UserID: transaction.UserID, AccountID: transaction.AccountID,
	}
	tokenRef, err := service.secrets.PutOAuthToken(ctx, binding, tokenSet.AccessToken)
	if err != nil {
		return OAuthCallbackResult{}, service.internalError("oauth_secret_store_failed", err)
	}
	connection := OAuthConnection{
		SchemaVersion: OAuthConnectionSchemaVersion, Provider: binding.Provider, TenantID: binding.TenantID,
		ProjectID: binding.ProjectID, SessionID: binding.SessionID, UserID: binding.UserID, AccountID: binding.AccountID,
		ProviderSubjectHash:    oauthProviderSubjectSHA256(binding.Provider, identity.Subject),
		ProviderSubjectPresent: true, DisplayName: identity.DisplayName,
		Email: identity.Email, EmailPresent: identity.Email != "", EmailVerified: identity.EmailVerified,
		TokenRef: tokenRef, ConnectedAt: service.now().UTC(),
	}
	var stored OAuthConnection
	if service.identityCoordinator != nil {
		stored, err = service.identityCoordinator.CompleteCallback(ctx, CompleteOAuthCallbackCommand{
			AccountID: transaction.AccountID, Provider: binding.Provider,
			ProviderSubject: identity.Subject, ActorID: transaction.UserID, Connection: connection,
		})
	} else {
		var identityLink OAuthIdentityLinkResult
		identityLink, err = service.identityBridge.LinkVerifiedOAuthCredential(
			ctx, transaction.AccountID, service.provider.Name(), identity.Subject, transaction.UserID,
		)
		if err == nil {
			connection.CredentialID = identityLink.Credential.CredentialID
			stored, err = service.connections.UpsertOAuthConnection(ctx, connection)
			if err != nil && identityLink.Created {
				_ = service.identityBridge.UnlinkOAuthCredential(
					context.Background(), transaction.AccountID, identityLink.Credential.CredentialID, transaction.UserID,
				)
			}
		}
	}
	if err != nil {
		if strings.TrimSpace(tokenSet.AccessToken) != "" {
			_ = service.provider.RevokeToken(ctx, credentials, tokenSet.AccessToken)
		}
		_ = service.secrets.DeleteOAuthToken(ctx, tokenRef)
		var oauthError OAuthError
		if errors.As(err, &oauthError) {
			return OAuthCallbackResult{}, oauthError
		}
		return OAuthCallbackResult{}, service.internalError("oauth_connection_store_failed", err)
	}
	return OAuthCallbackResult{SchemaVersion: service.provider.SchemaVersion(), Provider: binding.Provider, Connection: stored}, nil
}

func (service *OAuthService) Connection(ctx context.Context, request *http.Request, tenantID, projectID, accountID string) (OAuthConnection, error) {
	session, err := service.resolveActiveSession(ctx, request, tenantID)
	if err != nil {
		return OAuthConnection{}, err
	}
	accountID, err = canonicalOAuthAccountID(session.AccountID, accountID)
	if err != nil {
		return OAuthConnection{}, err
	}
	if err := validateOAuthBinding(tenantID, projectID, accountID); err != nil {
		return OAuthConnection{}, newOAuthPublicError(http.StatusBadRequest, "invalid_oauth_binding", err.Error(), err)
	}
	binding := OAuthSecretBinding{
		Provider: service.provider.Name(), TenantID: tenantID, ProjectID: projectID,
		SessionID: session.SessionID, UserID: session.UserID, AccountID: accountID,
	}
	connection, err := service.connections.GetOAuthConnection(ctx, binding)
	if err != nil {
		return OAuthConnection{}, newOAuthPublicError(http.StatusNotFound, "oauth_connection_not_found", "OAuth connection not found", err)
	}
	return connection, nil
}

func (service *OAuthService) Disconnect(ctx context.Context, request *http.Request, tenantID, projectID, accountID string) (OAuthDisconnectResult, error) {
	session, err := service.resolveActiveSession(ctx, request, tenantID)
	if err != nil {
		return OAuthDisconnectResult{}, err
	}
	accountID, err = canonicalOAuthAccountID(session.AccountID, accountID)
	if err != nil {
		return OAuthDisconnectResult{}, err
	}
	if err := validateOAuthBinding(tenantID, projectID, accountID); err != nil {
		return OAuthDisconnectResult{}, newOAuthPublicError(http.StatusBadRequest, "invalid_oauth_binding", err.Error(), err)
	}
	binding := OAuthSecretBinding{
		Provider: service.provider.Name(), TenantID: tenantID, ProjectID: projectID,
		SessionID: session.SessionID, UserID: session.UserID, AccountID: accountID,
	}
	connection, err := service.connections.GetOAuthConnection(ctx, binding)
	if err != nil {
		return OAuthDisconnectResult{}, newOAuthPublicError(http.StatusNotFound, "oauth_connection_not_found", "OAuth connection not found", err)
	}
	if err := service.identityBridge.ValidateOAuthCredentialUnlink(ctx, accountID, connection.CredentialID); err != nil {
		return OAuthDisconnectResult{}, err
	}
	var token string
	if connection.TokenRef != "" {
		token, err = service.secrets.GetOAuthToken(ctx, connection.TokenRef)
		if err != nil || strings.TrimSpace(token) == "" {
			return OAuthDisconnectResult{}, service.internalError("oauth_secret_resolve_failed", err)
		}
		credentials, credentialsErr := service.resolveCredentials(ctx)
		if credentialsErr != nil {
			return OAuthDisconnectResult{}, credentialsErr
		}
		if revokeErr := service.provider.RevokeToken(ctx, credentials, token); revokeErr != nil {
			return OAuthDisconnectResult{}, revokeErr
		}
	}
	var disconnected OAuthConnection
	if service.identityCoordinator != nil {
		disconnected, err = service.identityCoordinator.DisconnectCredential(ctx, DisconnectOAuthCredentialCommand{
			AccountID: accountID, ActorID: session.UserID, Binding: binding, Disconnected: service.now().UTC(),
		})
	} else {
		disconnected, err = service.connections.DisconnectOAuthConnection(ctx, binding, service.now().UTC())
		if err == nil {
			err = service.identityBridge.UnlinkOAuthCredential(ctx, accountID, connection.CredentialID, session.UserID)
		}
	}
	if err != nil {
		return OAuthDisconnectResult{}, err
	}
	if connection.TokenRef != "" {
		if deleteErr := service.secrets.DeleteOAuthToken(ctx, connection.TokenRef); deleteErr != nil {
			return OAuthDisconnectResult{}, service.internalError("oauth_secret_delete_failed", deleteErr)
		}
	}
	return OAuthDisconnectResult{
		SchemaVersion: service.provider.SchemaVersion(), Provider: service.provider.Name(),
		Disconnected: true, Connection: disconnected,
	}, nil
}

func (service *OAuthService) resolveActiveSession(ctx context.Context, request *http.Request, tenantID string) (OAuthSession, error) {
	session, err := service.sessionResolver.ResolveOAuthSession(ctx, request)
	if err != nil || session.Revoked || strings.TrimSpace(session.SessionID) == "" || strings.TrimSpace(session.UserID) == "" {
		return OAuthSession{}, newOAuthPublicError(http.StatusUnauthorized, "session_invalid", "an active authenticated session is required", err)
	}
	if strings.TrimSpace(session.TenantID) == "" || session.TenantID != tenantID {
		return OAuthSession{}, newOAuthPublicError(http.StatusForbidden, "tenant_mismatch", "tenant does not match the authenticated session", nil)
	}
	return session, nil
}

func canonicalOAuthAccountID(sessionAccountID, assertedAccountID string) (string, error) {
	sessionAccountID = strings.TrimSpace(sessionAccountID)
	assertedAccountID = strings.TrimSpace(assertedAccountID)
	if sessionAccountID == "" {
		return "", newOAuthPublicError(http.StatusUnauthorized, "session_account_missing", "authenticated session has no canonical account", nil)
	}
	if assertedAccountID != "" && assertedAccountID != sessionAccountID {
		return "", newOAuthPublicError(http.StatusForbidden, "account_mismatch", "account_id does not match the authenticated account", nil)
	}
	return sessionAccountID, nil
}

func (service *OAuthService) resolveCredentials(ctx context.Context) (OAuthClientCredentials, error) {
	credentials, err := service.credentials.OAuthCredentials(ctx, service.provider.Name())
	if err != nil || strings.TrimSpace(credentials.ClientID) == "" || strings.TrimSpace(credentials.ClientSecret) == "" {
		return OAuthClientCredentials{}, service.internalError("oauth_credentials_unavailable", err)
	}
	return credentials, nil
}

func (service *OAuthService) internalError(code string, cause error) OAuthError {
	return OAuthError{
		Status: http.StatusInternalServerError, Code: code,
		Message: fmt.Sprintf("%s OAuth request could not be completed", service.provider.Name()), Cause: cause,
	}
}

func newOAuthPublicError(status int, code, message string, cause error) OAuthError {
	return OAuthError{Status: status, Code: code, Message: message, Cause: cause}
}

func validateExactOAuthScopes(scopes []string) error {
	if len(scopes) == 0 {
		return fmt.Errorf("at least one scope is required")
	}
	seen := make(map[string]struct{}, len(scopes))
	for _, scope := range scopes {
		if strings.TrimSpace(scope) == "" || scope != strings.TrimSpace(scope) {
			return fmt.Errorf("scopes must be non-empty and normalized")
		}
		if _, exists := seen[scope]; exists {
			return fmt.Errorf("duplicate scope %q", scope)
		}
		seen[scope] = struct{}{}
	}
	return nil
}

func requireExactOAuthScopes(expected, actual []string) error {
	if err := validateExactOAuthScopes(expected); err != nil {
		return err
	}
	normalized := sortedUniqueStrings(actual)
	wanted := append([]string(nil), expected...)
	sort.Strings(wanted)
	if len(wanted) != len(normalized) {
		return fmt.Errorf("scope count mismatch")
	}
	for index := range wanted {
		if wanted[index] != normalized[index] {
			return fmt.Errorf("scope mismatch")
		}
	}
	return nil
}

func parseSpaceSeparatedScopes(raw string) []string {
	return sortedUniqueStrings(strings.Fields(raw))
}

func validateOAuthBinding(tenantID, projectID, accountID string) error {
	for name, value := range map[string]string{"tenant_id": tenantID, "project_id": projectID, "account_id": accountID} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("%s is required", name)
		}
	}
	return nil
}

func validateOAuthEndpoint(provider, name, raw string) (*url.URL, error) {
	endpoint, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || endpoint.Scheme != "https" || endpoint.Host == "" || endpoint.User != nil || endpoint.Fragment != "" {
		return nil, fmt.Errorf("%s OAuth %s endpoint must be an HTTPS URL", provider, name)
	}
	return endpoint, nil
}

type MemoryOAuthStore struct {
	mu            sync.Mutex
	transactions  map[string]OAuthTransaction
	secrets       map[string]string
	connections   map[string]OAuthConnection
	subjectOwners map[string]string
	random        io.Reader
}

func NewMemoryOAuthStore() *MemoryOAuthStore {
	return &MemoryOAuthStore{
		transactions: map[string]OAuthTransaction{}, secrets: map[string]string{},
		connections: map[string]OAuthConnection{}, subjectOwners: map[string]string{}, random: rand.Reader,
	}
}

func (store *MemoryOAuthStore) CreateOAuthTransaction(_ context.Context, transaction OAuthTransaction) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	key := transaction.Provider + "\x00" + transaction.StateHash
	if _, exists := store.transactions[key]; exists {
		return fmt.Errorf("OAuth state collision")
	}
	store.transactions[key] = transaction
	return nil
}

func (store *MemoryOAuthStore) ConsumeOAuthTransaction(_ context.Context, provider, stateHash string, now time.Time) (OAuthTransaction, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	key := provider + "\x00" + stateHash
	transaction, exists := store.transactions[key]
	if !exists {
		return OAuthTransaction{}, ErrOAuthTransactionNotFound
	}
	delete(store.transactions, key)
	if !now.Before(transaction.ExpiresAt) {
		return OAuthTransaction{}, ErrOAuthTransactionExpired
	}
	return transaction, nil
}

func (store *MemoryOAuthStore) PutOAuthToken(_ context.Context, binding OAuthSecretBinding, token string) (string, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	refToken, err := randomURLToken(store.random, 24)
	if err != nil {
		return "", err
	}
	ref := binding.Provider + "_oauth_ref_" + refToken
	store.secrets[ref] = token
	return ref, nil
}

func (store *MemoryOAuthStore) GetOAuthToken(_ context.Context, ref string) (string, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	token, exists := store.secrets[ref]
	if !exists {
		return "", fmt.Errorf("OAuth token reference was not found")
	}
	return token, nil
}

func (store *MemoryOAuthStore) DeleteOAuthToken(_ context.Context, ref string) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	delete(store.secrets, ref)
	return nil
}

func (store *MemoryOAuthStore) UpsertOAuthConnection(_ context.Context, connection OAuthConnection) (OAuthConnection, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	subjectKey := strings.ToLower(strings.TrimSpace(connection.Provider)) + ":" + connection.ProviderSubjectHash
	if owner, exists := store.subjectOwners[subjectKey]; exists && owner != connection.AccountID {
		return OAuthConnection{}, newOAuthPublicError(http.StatusConflict, "credential_link_conflict", "verified provider credential is already linked to another account", nil)
	}
	key := oauthBindingKey(OAuthSecretBinding{
		Provider: connection.Provider, TenantID: connection.TenantID, ProjectID: connection.ProjectID,
		SessionID: connection.SessionID, UserID: connection.UserID, AccountID: connection.AccountID,
	})
	if previous, exists := store.connections[key]; exists && previous.TokenRef != "" && previous.TokenRef != connection.TokenRef {
		delete(store.secrets, previous.TokenRef)
	}
	store.subjectOwners[subjectKey] = connection.AccountID
	store.connections[key] = connection
	return connection, nil
}

func (store *MemoryOAuthStore) GetOAuthConnection(_ context.Context, binding OAuthSecretBinding) (OAuthConnection, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	connection, exists := store.connections[oauthBindingKey(binding)]
	if !exists || connection.DisconnectedAt != nil {
		return OAuthConnection{}, ErrOAuthConnectionNotFound
	}
	return connection, nil
}

func (store *MemoryOAuthStore) DisconnectOAuthConnection(_ context.Context, binding OAuthSecretBinding, at time.Time) (OAuthConnection, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	key := oauthBindingKey(binding)
	connection, exists := store.connections[key]
	if !exists || connection.DisconnectedAt != nil {
		return OAuthConnection{}, ErrOAuthConnectionNotFound
	}
	connection.TokenRef = ""
	connection.DisconnectedAt = &at
	store.connections[key] = connection
	return connection, nil
}

func oauthBindingKey(binding OAuthSecretBinding) string {
	return strings.Join([]string{
		binding.Provider, binding.TenantID, binding.ProjectID, binding.SessionID, binding.UserID, binding.AccountID,
	}, "\x00")
}

func oauthProviderSubjectSHA256(provider, subject string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(provider) + ":" + strings.TrimSpace(subject)))
	return fmt.Sprintf("%x", sum[:])
}
