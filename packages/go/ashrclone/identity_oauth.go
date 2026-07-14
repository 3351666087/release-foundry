package ashrclone

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"net/url"
	"strings"
	"sync"
	"time"
)

type OAuthIntent string

const (
	OAuthIntentRegistration OAuthIntent = "registration"
	OAuthIntentLogin        OAuthIntent = "login"
	OAuthIntentLink         OAuthIntent = "link"
)

type OAuthFlowErrorCode string

const (
	OAuthInvalidRequest       OAuthFlowErrorCode = "oauth_invalid_request"
	OAuthProviderUnavailable  OAuthFlowErrorCode = "oauth_provider_unavailable"
	OAuthRedirectNotAllowed   OAuthFlowErrorCode = "oauth_redirect_not_allowed"
	OAuthInvalidOrExpiredFlow OAuthFlowErrorCode = "oauth_invalid_or_expired_flow"
	OAuthExchangeFailed       OAuthFlowErrorCode = "oauth_exchange_failed"
)

type OAuthFlowError struct {
	Code OAuthFlowErrorCode
}

func (err *OAuthFlowError) Error() string {
	return string(err.Code)
}

type OAuthAuthorizationRequest struct {
	Provider            string
	Intent              OAuthIntent
	RedirectURI         string
	State               string
	CodeChallenge       string
	CodeChallengeMethod string
}

type OAuthTokenExchangeRequest struct {
	Provider     string
	Intent       OAuthIntent
	RedirectURI  string
	Code         string
	PKCEVerifier string
}

// OAuthProviderIdentity is trusted adapter output. Raw provider identifiers and
// contact claims are intentionally excluded from JSON and must never be sent to
// A3 clients or logs.
type OAuthProviderIdentity struct {
	Provider        string `json:"-"`
	ProviderSubject string `json:"-"`
	ProviderUnionID string `json:"-"`
	VerifiedEmail   string `json:"-"`
	VerifiedPhone   string `json:"-"`
}

type OAuthProviderAdapter interface {
	BuildAuthorizationURL(context.Context, OAuthAuthorizationRequest) (string, error)
	ExchangeAuthorizationCode(context.Context, OAuthTokenExchangeRequest) (OAuthProviderIdentity, error)
}

type OAuthBeginResult struct {
	SchemaVersion    string      `json:"schema_version"`
	FlowID           string      `json:"flow_id"`
	Provider         string      `json:"provider"`
	Intent           OAuthIntent `json:"intent"`
	AuthorizationURL string      `json:"authorization_url"`
	ExpiresAt        time.Time   `json:"expires_at"`
}

type OAuthCompletionResult struct {
	SchemaVersion string
	FlowID        string
	Provider      string
	Intent        OAuthIntent
	AccountID     string
	Identity      OAuthProviderIdentity
}

type OAuthLinkCompletion struct {
	SchemaVersion string                `json:"schema_version"`
	Status        string                `json:"status"`
	Provider      string                `json:"provider"`
	BindingTicket IdentityBindingTicket `json:"binding_ticket"`
}

type oauthFlowRecord struct {
	ID           string
	Provider     string
	Intent       OAuthIntent
	AccountID    string
	RedirectURI  string
	StateHash    [32]byte
	PKCEVerifier string
	ExpiresAt    time.Time
}

// OAuthFlowCoordinator owns the browser-facing OAuth state machine. Provider
// adapters own provider-specific URLs and token exchange, while IdentityService
// remains the only authority allowed to issue account-bound binding tickets.
type OAuthFlowCoordinator struct {
	mu                sync.Mutex
	now               func() time.Time
	secret            func() (string, error)
	stateHMACKey      []byte
	identity          *IdentityService
	adapters          map[string]OAuthProviderAdapter
	redirectAllowlist map[string]map[string]struct{}
	flows             map[string]oauthFlowRecord
}

func NewOAuthFlowCoordinator(
	identity *IdentityService,
	adapters map[string]OAuthProviderAdapter,
	redirectAllowlist map[string][]string,
) (*OAuthFlowCoordinator, error) {
	key := make([]byte, 32)
	if _, err := rand.Read(key); err != nil {
		return nil, &OAuthFlowError{Code: OAuthProviderUnavailable}
	}
	return newOAuthFlowCoordinatorWithClockAndKey(identity, adapters, redirectAllowlist, time.Now, key)
}

func newOAuthFlowCoordinatorWithClockAndKey(
	identity *IdentityService,
	adapters map[string]OAuthProviderAdapter,
	redirectAllowlist map[string][]string,
	now func() time.Time,
	stateHMACKey []byte,
) (*OAuthFlowCoordinator, error) {
	if identity == nil || now == nil || len(stateHMACKey) < 32 {
		return nil, &OAuthFlowError{Code: OAuthInvalidRequest}
	}
	coordinator := &OAuthFlowCoordinator{
		now:               now,
		secret:            identitySecret,
		stateHMACKey:      append([]byte(nil), stateHMACKey...),
		identity:          identity,
		adapters:          map[string]OAuthProviderAdapter{},
		redirectAllowlist: map[string]map[string]struct{}{},
		flows:             map[string]oauthFlowRecord{},
	}
	for rawProvider, adapter := range adapters {
		provider := strings.ToLower(strings.TrimSpace(rawProvider))
		if provider == "" || adapter == nil || !providerSupportsOAuth(provider) {
			return nil, &OAuthFlowError{Code: OAuthInvalidRequest}
		}
		if _, exists := coordinator.adapters[provider]; exists {
			return nil, &OAuthFlowError{Code: OAuthInvalidRequest}
		}
		coordinator.adapters[provider] = adapter
	}
	for rawProvider, redirects := range redirectAllowlist {
		provider := strings.ToLower(strings.TrimSpace(rawProvider))
		if !providerSupportsOAuth(provider) {
			return nil, &OAuthFlowError{Code: OAuthInvalidRequest}
		}
		allowed := map[string]struct{}{}
		for _, rawRedirect := range redirects {
			redirect, err := normalizeOAuthRedirectURI(rawRedirect)
			if err != nil {
				return nil, err
			}
			allowed[redirect] = struct{}{}
		}
		coordinator.redirectAllowlist[provider] = allowed
	}
	return coordinator, nil
}

func (coordinator *OAuthFlowCoordinator) Begin(
	ctx context.Context,
	provider string,
	intent OAuthIntent,
	redirectURI string,
	accountID string,
) (OAuthBeginResult, error) {
	provider = strings.ToLower(strings.TrimSpace(provider))
	redirectURI, err := normalizeOAuthRedirectURI(redirectURI)
	if err != nil || !oauthIntentSupported(provider, intent) {
		return OAuthBeginResult{}, &OAuthFlowError{Code: OAuthInvalidRequest}
	}
	if intent == OAuthIntentLink && strings.TrimSpace(accountID) == "" {
		return OAuthBeginResult{}, &OAuthFlowError{Code: OAuthInvalidRequest}
	}
	adapter, exists := coordinator.adapters[provider]
	if !exists {
		return OAuthBeginResult{}, &OAuthFlowError{Code: OAuthProviderUnavailable}
	}
	if _, allowed := coordinator.redirectAllowlist[provider][redirectURI]; !allowed {
		return OAuthBeginResult{}, &OAuthFlowError{Code: OAuthRedirectNotAllowed}
	}

	flowID, err := coordinator.secret()
	if err != nil {
		return OAuthBeginResult{}, &OAuthFlowError{Code: OAuthProviderUnavailable}
	}
	state, err := coordinator.secret()
	if err != nil {
		return OAuthBeginResult{}, &OAuthFlowError{Code: OAuthProviderUnavailable}
	}
	verifier, err := coordinator.secret()
	if err != nil {
		return OAuthBeginResult{}, &OAuthFlowError{Code: OAuthProviderUnavailable}
	}
	challengeDigest := sha256.Sum256([]byte(verifier))
	codeChallenge := base64.RawURLEncoding.EncodeToString(challengeDigest[:])
	authorizationURL, err := adapter.BuildAuthorizationURL(ctx, OAuthAuthorizationRequest{
		Provider:            provider,
		Intent:              intent,
		RedirectURI:         redirectURI,
		State:               state,
		CodeChallenge:       codeChallenge,
		CodeChallengeMethod: "S256",
	})
	if err != nil || strings.TrimSpace(authorizationURL) == "" {
		return OAuthBeginResult{}, &OAuthFlowError{Code: OAuthProviderUnavailable}
	}

	now := coordinator.now().UTC()
	record := oauthFlowRecord{
		ID:           flowID,
		Provider:     provider,
		Intent:       intent,
		AccountID:    strings.TrimSpace(accountID),
		RedirectURI:  redirectURI,
		StateHash:    oauthStateHMAC(coordinator.stateHMACKey, state),
		PKCEVerifier: verifier,
		ExpiresAt:    now.Add(10 * time.Minute),
	}
	coordinator.mu.Lock()
	coordinator.pruneExpiredFlowsLocked(now)
	coordinator.flows[flowID] = record
	coordinator.mu.Unlock()
	return OAuthBeginResult{
		SchemaVersion:    IdentitySchemaVersion,
		FlowID:           flowID,
		Provider:         provider,
		Intent:           intent,
		AuthorizationURL: authorizationURL,
		ExpiresAt:        record.ExpiresAt,
	}, nil
}

func (coordinator *OAuthFlowCoordinator) Complete(
	ctx context.Context,
	flowID string,
	state string,
	code string,
) (OAuthCompletionResult, error) {
	flowID = strings.TrimSpace(flowID)
	if flowID == "" || strings.TrimSpace(state) == "" || strings.TrimSpace(code) == "" {
		return OAuthCompletionResult{}, &OAuthFlowError{Code: OAuthInvalidRequest}
	}

	coordinator.mu.Lock()
	record, exists := coordinator.flows[flowID]
	now := coordinator.now().UTC()
	candidateState := oauthStateHMAC(coordinator.stateHMACKey, state)
	if !exists ||
		!now.Before(record.ExpiresAt) ||
		!hmac.Equal(candidateState[:], record.StateHash[:]) {
		coordinator.mu.Unlock()
		return OAuthCompletionResult{}, &OAuthFlowError{Code: OAuthInvalidOrExpiredFlow}
	}
	// Consume before exchange so a failed or interrupted exchange cannot be
	// replayed with the same state/code pair.
	delete(coordinator.flows, flowID)
	coordinator.mu.Unlock()

	adapter, exists := coordinator.adapters[record.Provider]
	if !exists {
		return OAuthCompletionResult{}, &OAuthFlowError{Code: OAuthProviderUnavailable}
	}
	identity, err := adapter.ExchangeAuthorizationCode(ctx, OAuthTokenExchangeRequest{
		Provider:     record.Provider,
		Intent:       record.Intent,
		RedirectURI:  record.RedirectURI,
		Code:         code,
		PKCEVerifier: record.PKCEVerifier,
	})
	if err != nil {
		return OAuthCompletionResult{}, &OAuthFlowError{Code: OAuthExchangeFailed}
	}
	identity.Provider = strings.ToLower(strings.TrimSpace(identity.Provider))
	if identity.Provider == "" {
		identity.Provider = record.Provider
	}
	if identity.Provider != record.Provider || strings.TrimSpace(identity.ProviderSubject) == "" {
		return OAuthCompletionResult{}, &OAuthFlowError{Code: OAuthExchangeFailed}
	}
	return OAuthCompletionResult{
		SchemaVersion: IdentitySchemaVersion,
		FlowID:        record.ID,
		Provider:      record.Provider,
		Intent:        record.Intent,
		AccountID:     record.AccountID,
		Identity:      identity,
	}, nil
}

func (coordinator *OAuthFlowCoordinator) pruneExpiredFlowsLocked(now time.Time) {
	for flowID, record := range coordinator.flows {
		if !now.Before(record.ExpiresAt) {
			delete(coordinator.flows, flowID)
		}
	}
}

func (coordinator *OAuthFlowCoordinator) CompleteLink(
	ctx context.Context,
	flowID string,
	state string,
	code string,
) (OAuthLinkCompletion, error) {
	completed, err := coordinator.Complete(ctx, flowID, state, code)
	if err != nil {
		return OAuthLinkCompletion{}, err
	}
	return coordinator.linkCompletionFromValidated(completed)
}

func (coordinator *OAuthFlowCoordinator) linkCompletionFromValidated(
	completed OAuthCompletionResult,
) (OAuthLinkCompletion, error) {
	if completed.Intent != OAuthIntentLink || completed.AccountID == "" {
		return OAuthLinkCompletion{}, &OAuthFlowError{Code: OAuthInvalidRequest}
	}
	ticket, err := coordinator.identity.IssueCredentialBindingTicket(completed.AccountID, BindCredentialRequest{
		Provider:        completed.Identity.Provider,
		ProviderSubject: completed.Identity.ProviderSubject,
		ProviderUnionID: completed.Identity.ProviderUnionID,
		VerifiedEmail:   completed.Identity.VerifiedEmail,
		VerifiedPhone:   completed.Identity.VerifiedPhone,
	})
	if err != nil {
		return OAuthLinkCompletion{}, err
	}
	return OAuthLinkCompletion{
		SchemaVersion: IdentitySchemaVersion,
		Status:        "binding_ticket_issued",
		Provider:      completed.Provider,
		BindingTicket: ticket,
	}, nil
}

func oauthStateHMAC(key []byte, value string) [32]byte {
	mac := hmac.New(sha256.New, key)
	_, _ = mac.Write([]byte(value))
	var result [32]byte
	copy(result[:], mac.Sum(nil))
	return result
}

func oauthIntentSupported(provider string, intent OAuthIntent) bool {
	for _, capability := range IdentityProviderCapabilities() {
		if capability.Provider != provider || !capability.Enabled {
			continue
		}
		switch intent {
		case OAuthIntentRegistration:
			return capability.SupportsRegistration
		case OAuthIntentLogin:
			return capability.SupportsLogin
		case OAuthIntentLink:
			return capability.SupportsExplicitBinding
		default:
			return false
		}
	}
	return false
}

func providerSupportsOAuth(provider string) bool {
	for _, capability := range IdentityProviderCapabilities() {
		if capability.Provider == provider {
			return capability.Enabled && (capability.Kind == "oauth2" || capability.Kind == "oidc")
		}
	}
	return false
}

func normalizeOAuthRedirectURI(raw string) (string, error) {
	value := strings.TrimSpace(raw)
	parsed, err := url.Parse(value)
	if err != nil ||
		parsed.IsAbs() == false ||
		parsed.Host == "" ||
		parsed.User != nil ||
		parsed.Fragment != "" {
		return "", &OAuthFlowError{Code: OAuthRedirectNotAllowed}
	}
	host := strings.ToLower(parsed.Hostname())
	secure := strings.EqualFold(parsed.Scheme, "https")
	loopback := strings.EqualFold(parsed.Scheme, "http") &&
		(host == "localhost" || host == "127.0.0.1" || host == "::1")
	if !secure && !loopback {
		return "", &OAuthFlowError{Code: OAuthRedirectNotAllowed}
	}
	return parsed.String(), nil
}
