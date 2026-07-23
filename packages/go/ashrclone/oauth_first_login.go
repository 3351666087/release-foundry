package ashrclone

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const (
	OAuthFirstLoginSchemaVersion              = "ashr.oauth_first_login.v1"
	OAuthPurposeFirstLogin       OAuthPurpose = "first_login"
)

// OAuthPurpose is server-selected. Public first-login endpoints never accept
// a purpose from the browser, and authenticated credential binding uses the
// separate OAuthService path.
type OAuthPurpose string

type OAuthFirstLoginTransaction struct {
	Provider       string
	Purpose        OAuthPurpose
	StateHash      string
	CodeVerifier   string
	Nonce          string
	IntentID       string
	OrganizationID string
	ProjectID      string
	CreatedAt      time.Time
	ExpiresAt      time.Time
}

type OAuthFirstLoginTransactionStore interface {
	CreateOAuthFirstLoginTransaction(context.Context, OAuthFirstLoginTransaction) error
	ConsumeOAuthFirstLoginTransaction(
		context.Context,
		string,
		string,
		time.Time,
	) (OAuthFirstLoginTransaction, error)
}

// OAuthFirstLoginCompletionCommand contains only provider-verified identity
// material and server-selected scope. Implementations own the atomic canonical
// account/login decision; verified email is conflict evidence, never an
// instruction to merge accounts.
type OAuthFirstLoginCompletionCommand struct {
	SchemaVersion   string
	Purpose         OAuthPurpose
	OrganizationID  string
	ProjectID       string
	Provider        string
	ProviderSubject string
	DisplayName     string
	VerifiedEmail   string
	TokenRef        string
	CompletedAt     time.Time
}

type OAuthFirstLoginCompletionResult struct {
	SchemaVersion string    `json:"schema_version"`
	Provider      string    `json:"provider"`
	AccountID     string    `json:"account_id"`
	CredentialID  string    `json:"credential_id"`
	SessionID     string    `json:"session_id"`
	Created       bool      `json:"created"`
	CompletedAt   time.Time `json:"completed_at"`
}

type OAuthFirstLoginCoordinator interface {
	CompleteOAuthFirstLogin(
		context.Context,
		OAuthFirstLoginCompletionCommand,
	) (OAuthFirstLoginCompletionResult, IdentitySessionIssuanceReceipt, error)
}

type OAuthFirstLoginServiceOptions struct {
	Provider       OAuthProviderAdapter
	Credentials    OAuthCredentialsProvider
	Transactions   OAuthFirstLoginTransactionStore
	Secrets        OAuthSecretStore
	Coordinator    OAuthFirstLoginCoordinator
	OrganizationID string
	ProjectID      string
	CallbackURL    string
	TransactionTTL time.Duration
	Now            func() time.Time
	Random         io.Reader
}

type OAuthFirstLoginService struct {
	provider       OAuthProviderAdapter
	credentials    OAuthCredentialsProvider
	transactions   OAuthFirstLoginTransactionStore
	secrets        OAuthSecretStore
	coordinator    OAuthFirstLoginCoordinator
	organizationID string
	projectID      string
	callbackURL    string
	callbackHost   string
	transactionTTL time.Duration
	now            func() time.Time
	random         io.Reader
}

type oauthFirstLoginPreparedStart struct {
	AuthorizationURL string
	Transaction      OAuthFirstLoginTransaction
}

func NewOAuthFirstLoginService(
	options OAuthFirstLoginServiceOptions,
) (*OAuthFirstLoginService, error) {
	if options.Provider == nil || options.Credentials == nil ||
		options.Transactions == nil || options.Secrets == nil ||
		options.Coordinator == nil {
		return nil, fmt.Errorf("OAuth first-login provider, credentials, transaction, secret, and canonical coordinators are required")
	}
	provider := strings.ToLower(strings.TrimSpace(options.Provider.Name()))
	if !validOAuthFirstLoginHandle(provider, 64) ||
		provider != options.Provider.Name() {
		return nil, fmt.Errorf("OAuth first-login provider name must be normalized")
	}
	if err := validateExactOAuthScopes(options.Provider.ExactScopes()); err != nil {
		return nil, fmt.Errorf("%s OAuth first-login scopes: %w", provider, err)
	}
	organizationID := strings.TrimSpace(options.OrganizationID)
	projectID := strings.TrimSpace(options.ProjectID)
	if !validOAuthFirstLoginHandle(organizationID, 256) ||
		!validOAuthFirstLoginHandle(projectID, 256) {
		return nil, fmt.Errorf("OAuth first-login trusted organization and project scope are required")
	}
	callback, err := validateOAuthEndpoint(provider, "first-login callback", options.CallbackURL)
	if err != nil || callback.RawQuery != "" || callback.Path !=
		"/v1/identity/oauth/"+url.PathEscape(provider)+"/callback" {
		return nil, fmt.Errorf("OAuth first-login callback URL must be the dedicated provider callback")
	}
	transactionTTL := options.TransactionTTL
	if transactionTTL == 0 {
		transactionTTL = 10 * time.Minute
	}
	if transactionTTL < time.Second || transactionTTL > 30*time.Minute {
		return nil, fmt.Errorf("OAuth first-login transaction lifetime must be between one second and 30 minutes")
	}
	now := options.Now
	if now == nil {
		now = time.Now
	}
	random := options.Random
	if random == nil {
		random = rand.Reader
	}
	return &OAuthFirstLoginService{
		provider:       options.Provider,
		credentials:    options.Credentials,
		transactions:   options.Transactions,
		secrets:        options.Secrets,
		coordinator:    options.Coordinator,
		organizationID: organizationID,
		projectID:      projectID,
		callbackURL:    callback.String(),
		callbackHost:   strings.ToLower(callback.Host),
		transactionTTL: transactionTTL,
		now:            now,
		random:         random,
	}, nil
}

func (service *OAuthFirstLoginService) ProviderName() string {
	if service == nil || service.provider == nil {
		return ""
	}
	return strings.ToLower(strings.TrimSpace(service.provider.Name()))
}

func (service *OAuthFirstLoginService) MatchesCallbackHost(host string) bool {
	return service != nil && host != "" && host == strings.TrimSpace(host) &&
		strings.EqualFold(host, service.callbackHost)
}

// prepareStart performs all fallible provider configuration work before the
// browser intent or one-time transaction is persisted.
func (service *OAuthFirstLoginService) prepareStart(
	ctx context.Context,
) (oauthFirstLoginPreparedStart, error) {
	credentials, err := service.resolveCredentials(ctx)
	if err != nil {
		return oauthFirstLoginPreparedStart{}, err
	}
	state, err := randomURLToken(service.random, 32)
	if err != nil {
		return oauthFirstLoginPreparedStart{}, service.internalError("oauth_first_login_start_failed", err)
	}
	verifier, err := randomURLToken(service.random, 48)
	if err != nil {
		return oauthFirstLoginPreparedStart{}, service.internalError("oauth_first_login_start_failed", err)
	}
	nonce, err := randomURLToken(service.random, 32)
	if err != nil {
		return oauthFirstLoginPreparedStart{}, service.internalError("oauth_first_login_start_failed", err)
	}
	intentToken, err := randomURLToken(service.random, 24)
	if err != nil {
		return oauthFirstLoginPreparedStart{}, service.internalError("oauth_first_login_start_failed", err)
	}
	now := service.now().UTC()
	transaction := OAuthFirstLoginTransaction{
		Provider:       service.ProviderName(),
		Purpose:        OAuthPurposeFirstLogin,
		StateHash:      stateSHA256(state),
		CodeVerifier:   verifier,
		Nonce:          nonce,
		IntentID:       "ofli_" + intentToken,
		OrganizationID: service.organizationID,
		ProjectID:      service.projectID,
		CreatedAt:      now,
		ExpiresAt:      now.Add(service.transactionTTL),
	}
	authorizationURL, err := service.provider.AuthorizationURL(OAuthAuthorizationRequest{
		ClientID:      credentials.ClientID,
		CallbackURL:   service.callbackURL,
		State:         state,
		CodeChallenge: pkceS256(verifier),
		Nonce:         nonce,
		Scopes:        append([]string(nil), service.provider.ExactScopes()...),
	})
	if err != nil || strings.TrimSpace(authorizationURL) == "" {
		return oauthFirstLoginPreparedStart{}, service.internalError("oauth_first_login_configuration_invalid", err)
	}
	return oauthFirstLoginPreparedStart{
		AuthorizationURL: authorizationURL,
		Transaction:      transaction,
	}, nil
}

func (service *OAuthFirstLoginService) commitStart(
	ctx context.Context,
	transaction OAuthFirstLoginTransaction,
) error {
	if !service.validTransaction(transaction) {
		return service.internalError("oauth_first_login_transaction_invalid", nil)
	}
	if err := service.transactions.CreateOAuthFirstLoginTransaction(ctx, transaction); err != nil {
		return service.internalError("oauth_first_login_start_failed", err)
	}
	return nil
}

func (service *OAuthFirstLoginService) complete(
	ctx context.Context,
	code string,
	state string,
	validateIntent func(OAuthFirstLoginTransaction) error,
) (OAuthFirstLoginCompletionResult, IdentitySessionIssuanceReceipt, error) {
	if code == "" || code != strings.TrimSpace(code) ||
		state == "" || state != strings.TrimSpace(state) {
		return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{},
			newOAuthPublicError(http.StatusBadRequest, "invalid_oauth_callback", "OAuth callback is invalid", nil)
	}
	transaction, err := service.transactions.ConsumeOAuthFirstLoginTransaction(
		ctx,
		service.ProviderName(),
		stateSHA256(state),
		service.now().UTC(),
	)
	if err != nil || !service.validTransaction(transaction) {
		return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{},
			newOAuthPublicError(http.StatusBadRequest, "invalid_oauth_state", "OAuth state is invalid, expired, or already used", err)
	}
	if validateIntent == nil || validateIntent(transaction) != nil {
		return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{},
			newOAuthPublicError(http.StatusForbidden, "oauth_first_login_intent_rejected", "OAuth browser intent was rejected", nil)
	}
	credentials, err := service.resolveCredentials(ctx)
	if err != nil {
		return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{}, err
	}
	tokenSet, err := service.provider.ExchangeCode(ctx, OAuthCodeExchangeRequest{
		Credentials:  credentials,
		CallbackURL:  service.callbackURL,
		Code:         code,
		CodeVerifier: transaction.CodeVerifier,
	})
	if err != nil || strings.TrimSpace(tokenSet.AccessToken) == "" {
		return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{},
			newOAuthPublicError(http.StatusBadGateway, "oauth_first_login_exchange_failed", "OAuth provider exchange failed", err)
	}
	cleanupToken := true
	defer func() {
		if cleanupToken {
			_ = service.provider.RevokeToken(context.Background(), credentials, tokenSet.AccessToken)
		}
	}()
	if err := requireExactOAuthScopes(service.provider.ExactScopes(), tokenSet.Scopes); err != nil {
		return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{},
			newOAuthPublicError(http.StatusBadGateway, "oauth_first_login_scope_mismatch", "OAuth provider scope validation failed", err)
	}
	identity, err := service.provider.ResolveIdentity(ctx, OAuthIdentityRequest{
		TokenSet: tokenSet,
		Nonce:    transaction.Nonce,
		ClientID: credentials.ClientID,
		Now:      service.now().UTC(),
	})
	if err != nil {
		return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{},
			newOAuthPublicError(http.StatusBadGateway, "oauth_first_login_identity_invalid", "OAuth provider identity validation failed", err)
	}
	providerSubject := strings.TrimSpace(identity.Subject)
	if !validOAuthFirstLoginHandle(providerSubject, 1024) ||
		providerSubject != identity.Subject {
		return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{},
			newOAuthPublicError(http.StatusBadGateway, "oauth_first_login_identity_invalid", "OAuth provider identity validation failed", nil)
	}
	verifiedEmail := ""
	if identity.Email != "" {
		if !identity.EmailVerified {
			return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{},
				newOAuthPublicError(http.StatusBadGateway, "oauth_first_login_identity_invalid", "OAuth provider identity validation failed", nil)
		}
		verifiedEmail, err = normalizeIdentityEmail(identity.Email)
		if err != nil || verifiedEmail != identity.Email {
			return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{},
				newOAuthPublicError(http.StatusBadGateway, "oauth_first_login_identity_invalid", "OAuth provider identity validation failed", err)
		}
	}
	temporaryHandle := "oauth_first_login:" + transaction.IntentID
	tokenRef, err := service.secrets.PutOAuthToken(ctx, OAuthSecretBinding{
		Provider:  transaction.Provider,
		TenantID:  transaction.OrganizationID,
		ProjectID: transaction.ProjectID,
		SessionID: temporaryHandle,
		UserID:    temporaryHandle,
		AccountID: temporaryHandle,
	}, tokenSet.AccessToken)
	if err != nil || !validOAuthFirstLoginHandle(tokenRef, 1024) {
		return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{},
			service.internalError("oauth_first_login_secret_store_failed", err)
	}
	deleteSecret := true
	defer func() {
		if deleteSecret {
			_ = service.secrets.DeleteOAuthToken(context.Background(), tokenRef)
		}
	}()
	completedAt := service.now().UTC()
	result, receipt, err := service.coordinator.CompleteOAuthFirstLogin(
		ctx,
		OAuthFirstLoginCompletionCommand{
			SchemaVersion:   OAuthFirstLoginSchemaVersion,
			Purpose:         OAuthPurposeFirstLogin,
			OrganizationID:  transaction.OrganizationID,
			ProjectID:       transaction.ProjectID,
			Provider:        transaction.Provider,
			ProviderSubject: providerSubject,
			DisplayName:     strings.TrimSpace(identity.DisplayName),
			VerifiedEmail:   verifiedEmail,
			TokenRef:        tokenRef,
			CompletedAt:     completedAt,
		},
	)
	if err != nil {
		var oauthError OAuthError
		if errors.As(err, &oauthError) {
			return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{}, oauthError
		}
		return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{},
			service.internalError("oauth_first_login_canonical_mutation_failed", err)
	}
	if result.SchemaVersion != OAuthFirstLoginSchemaVersion ||
		result.Provider != transaction.Provider ||
		!validOAuthFirstLoginHandle(result.AccountID, 256) ||
		!validOAuthFirstLoginHandle(result.CredentialID, 256) ||
		!validOAuthFirstLoginHandle(result.SessionID, 256) {
		return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{},
			service.internalError("oauth_first_login_canonical_result_invalid", nil)
	}
	cleanupToken = false
	deleteSecret = false
	return result, receipt, nil
}

func (service *OAuthFirstLoginService) resolveCredentials(
	ctx context.Context,
) (OAuthClientCredentials, error) {
	credentials, err := service.credentials.OAuthCredentials(ctx, service.ProviderName())
	if err != nil || strings.TrimSpace(credentials.ClientID) == "" ||
		strings.TrimSpace(credentials.ClientSecret) == "" {
		return OAuthClientCredentials{}, service.internalError("oauth_first_login_credentials_unavailable", err)
	}
	return credentials, nil
}

func (service *OAuthFirstLoginService) validTransaction(
	transaction OAuthFirstLoginTransaction,
) bool {
	return service != nil && transaction.Provider == service.ProviderName() &&
		transaction.Purpose == OAuthPurposeFirstLogin &&
		transaction.OrganizationID == service.organizationID &&
		transaction.ProjectID == service.projectID &&
		validOAuthFirstLoginHandle(transaction.StateHash, 128) &&
		validOAuthFirstLoginHandle(transaction.CodeVerifier, 256) &&
		validOAuthFirstLoginHandle(transaction.Nonce, 256) &&
		validOAuthFirstLoginHandle(transaction.IntentID, 256) &&
		!transaction.CreatedAt.IsZero() && transaction.ExpiresAt.After(transaction.CreatedAt) &&
		!transaction.ExpiresAt.After(transaction.CreatedAt.Add(service.transactionTTL))
}

func (service *OAuthFirstLoginService) internalError(code string, cause error) OAuthError {
	return OAuthError{
		Status:  http.StatusInternalServerError,
		Code:    code,
		Message: service.ProviderName() + " OAuth first login could not be completed",
		Cause:   cause,
	}
}

func validOAuthFirstLoginHandle(value string, maximum int) bool {
	return value != "" && value == strings.TrimSpace(value) && len(value) <= maximum &&
		!strings.ContainsAny(value, "\x00\r\n\t")
}
