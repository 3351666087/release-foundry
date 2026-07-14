package ashrclone

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"
)

const IdentitySchemaVersion = "ashr.clone.identity.v1"

type IdentityErrorCode string

const (
	IdentityInvalidInput         IdentityErrorCode = "invalid_input"
	IdentityInvalidProof         IdentityErrorCode = "invalid_or_expired_proof"
	IdentityRegistrationConflict IdentityErrorCode = "registration_conflict"
	IdentityBindingConflict      IdentityErrorCode = "credential_binding_conflict"
	IdentityConsentRequired      IdentityErrorCode = "explicit_binding_consent_required"
	IdentityReauthRequired       IdentityErrorCode = "reauthentication_required"
	IdentityNotFound             IdentityErrorCode = "account_not_found"
	IdentityUnavailable          IdentityErrorCode = "identity_service_unavailable"
	IdentityHashKeyInvalid       IdentityErrorCode = "identity_hash_key_invalid"
	IdentityHashKeyInUse         IdentityErrorCode = "identity_hash_key_in_use"
)

type IdentityError struct {
	Code IdentityErrorCode
}

func (err *IdentityError) Error() string {
	return string(err.Code)
}

type IdentityProviderCapability struct {
	Provider                string `json:"provider"`
	Kind                    string `json:"kind"`
	Enabled                 bool   `json:"enabled"`
	Region                  string `json:"region"`
	SupportsRegistration    bool   `json:"supports_registration"`
	SupportsLogin           bool   `json:"supports_login"`
	SupportsExplicitBinding bool   `json:"supports_explicit_binding"`
	PKCERequired            bool   `json:"pkce_required"`
}

type CanonicalAccount struct {
	SchemaVersion    string    `json:"schema_version"`
	AccountID        string    `json:"account_id"`
	PrimaryEmail     string    `json:"primary_email"`
	DisplayName      string    `json:"display_name,omitempty"`
	Locale           string    `json:"locale"`
	Region           string    `json:"region"`
	Status           string    `json:"status"`
	TwoFactor        bool      `json:"two_factor_enabled"`
	TwoFactorMethods []string  `json:"two_factor_methods,omitempty"`
	CreatedAt        time.Time `json:"created_at"`
	UpdatedAt        time.Time `json:"updated_at"`
}

type IdentityCredential struct {
	SchemaVersion              string    `json:"schema_version"`
	CredentialID               string    `json:"credential_id"`
	AccountID                  string    `json:"account_id"`
	Provider                   string    `json:"provider"`
	ProviderSubjectFingerprint string    `json:"-"`
	ProviderUnionFingerprint   string    `json:"-"`
	VerifiedEmail              string    `json:"-"`
	VerifiedPhone              string    `json:"-"`
	CreatedAt                  time.Time `json:"created_at"`
	LastLoginAt                time.Time `json:"last_login_at,omitempty"`
}

type IdentityChallenge struct {
	SchemaVersion  string    `json:"schema_version"`
	ChallengeID    string    `json:"challenge_id"`
	Purpose        string    `json:"purpose"`
	DeliveryMethod string    `json:"delivery_method"`
	DeliveryHint   string    `json:"delivery_hint"`
	ExpiresAt      time.Time `json:"expires_at"`
	Secret         string    `json:"-"`
}

type CompleteRegistrationRequest struct {
	ChallengeID string
	Secret      string
	DisplayName string
}

type BindCredentialRequest struct {
	Provider        string
	ProviderSubject string
	ProviderUnionID string
	VerifiedEmail   string
	VerifiedPhone   string
	ExplicitConsent bool
	Reauthenticated bool
}

type LoginResult struct {
	SchemaVersion     string    `json:"schema_version"`
	Status            string    `json:"status"`
	AccountID         string    `json:"account_id,omitempty"`
	SessionID         string    `json:"session_id,omitempty"`
	MFAChallengeID    string    `json:"mfa_challenge_id,omitempty"`
	ExpiresAt         time.Time `json:"expires_at,omitempty"`
	SessionToken      string    `json:"-"`
	MFASecret         string    `json:"-"`
	MFADeliveryTarget string    `json:"-"`
}

type IdentityBindingTicket struct {
	SchemaVersion string    `json:"schema_version"`
	TicketID      string    `json:"ticket_id"`
	Provider      string    `json:"provider"`
	ExpiresAt     time.Time `json:"expires_at"`
	Secret        string    `json:"-"`
}

type A3CredentialView struct {
	Provider string `json:"provider"`
	Kind     string `json:"kind"`
}

type A3TwoFactorView struct {
	Enabled     bool     `json:"enabled"`
	Recommended bool     `json:"recommended"`
	Methods     []string `json:"methods"`
}

type A3IdentityView struct {
	SchemaVersion               string                       `json:"schema_version"`
	AccountID                   string                       `json:"account_id"`
	PrimaryEmailHint            string                       `json:"primary_email_hint"`
	DisplayName                 string                       `json:"display_name,omitempty"`
	Locale                      string                       `json:"locale"`
	Region                      string                       `json:"region"`
	Status                      string                       `json:"status"`
	PreferredRegistrationMethod string                       `json:"preferred_registration_method"`
	Credentials                 []A3CredentialView           `json:"credentials"`
	TwoFactor                   A3TwoFactorView              `json:"two_factor"`
	ProviderCapabilities        []IdentityProviderCapability `json:"provider_capabilities"`
}

type identityChallengeRecord struct {
	ID              string
	Purpose         string
	Email           string
	Locale          string
	Region          string
	SecretHash      [32]byte
	SecretHashKeyID string
	ExpiresAt       time.Time
	Consumed        bool
	AccountID       string
}

type identitySessionRecord struct {
	ID              string
	AccountID       string
	TokenHash       [32]byte
	TokenHashKeyID  string
	AuthenticatedAt time.Time
	ExpiresAt       time.Time
	Revoked         bool
}

type identityBindingTicketRecord struct {
	ID              string
	AccountID       string
	Request         BindCredentialRequest
	SecretHash      [32]byte
	SecretHashKeyID string
	ExpiresAt       time.Time
	Consumed        bool
}

type IdentityService struct {
	mu                 sync.Mutex
	now                func() time.Time
	secret             func() (string, error)
	accounts           map[string]CanonicalAccount
	credentials        map[string]IdentityCredential
	credentialBindings map[string]string
	accountCredentials map[string][]string
	challenges         map[string]identityChallengeRecord
	sessions           map[string]identitySessionRecord
	bindingTickets     map[string]identityBindingTicketRecord
	hashKeys           map[string][]byte
	activeHashKeyID    string
	nextID             int
}

func NewIdentityService() *IdentityService {
	return NewIdentityServiceWithClock(time.Now)
}

func NewIdentityServiceWithClock(now func() time.Time) *IdentityService {
	if now == nil {
		now = time.Now
	}
	service := &IdentityService{
		now:                now,
		secret:             identitySecret,
		accounts:           map[string]CanonicalAccount{},
		credentials:        map[string]IdentityCredential{},
		credentialBindings: map[string]string{},
		accountCredentials: map[string][]string{},
		challenges:         map[string]identityChallengeRecord{},
		sessions:           map[string]identitySessionRecord{},
		bindingTickets:     map[string]identityBindingTicketRecord{},
		hashKeys:           map[string][]byte{},
		nextID:             1,
	}
	if key, err := identityHashKey(); err == nil {
		service.hashKeys["identity-hmac-v1"] = key
		service.activeHashKeyID = "identity-hmac-v1"
	}
	return service
}

// NewIdentityServiceWithHashKey creates an identity service with an explicit
// initial HMAC key. It is intended for durable deployments that load key
// material from a secret manager and for deterministic rotation tests.
func NewIdentityServiceWithHashKey(now func() time.Time, keyID string, key []byte) (*IdentityService, error) {
	service := NewIdentityServiceWithClock(now)
	service.hashKeys = map[string][]byte{}
	service.activeHashKeyID = ""
	if err := service.rotateHashKeyLocked(keyID, key); err != nil {
		return nil, err
	}
	return service, nil
}

// RotateHashKey installs a new HMAC key and makes it active for newly issued
// challenge proofs and sessions. Records issued under older keys continue to
// verify by their stored key ID.
func (service *IdentityService) RotateHashKey(keyID string, key []byte) error {
	service.mu.Lock()
	defer service.mu.Unlock()
	return service.rotateHashKeyLocked(keyID, key)
}

// RetireHashKey removes an inactive HMAC key only after every challenge and
// session that still requires it is consumed, expired, or revoked.
func (service *IdentityService) RetireHashKey(keyID string) error {
	service.mu.Lock()
	defer service.mu.Unlock()
	keyID = strings.TrimSpace(keyID)
	if keyID == "" || keyID == service.activeHashKeyID {
		return &IdentityError{Code: IdentityHashKeyInUse}
	}
	if _, exists := service.hashKeys[keyID]; !exists {
		return &IdentityError{Code: IdentityHashKeyInvalid}
	}
	now := service.now().UTC()
	for _, challenge := range service.challenges {
		if challenge.SecretHashKeyID == keyID && !challenge.Consumed && now.Before(challenge.ExpiresAt) {
			return &IdentityError{Code: IdentityHashKeyInUse}
		}
	}
	for _, session := range service.sessions {
		if session.TokenHashKeyID == keyID && !session.Revoked && now.Before(session.ExpiresAt) {
			return &IdentityError{Code: IdentityHashKeyInUse}
		}
	}
	for _, ticket := range service.bindingTickets {
		if ticket.SecretHashKeyID == keyID && !ticket.Consumed && now.Before(ticket.ExpiresAt) {
			return &IdentityError{Code: IdentityHashKeyInUse}
		}
	}
	delete(service.hashKeys, keyID)
	return nil
}

func IdentityProviderCapabilities() []IdentityProviderCapability {
	return []IdentityProviderCapability{
		{Provider: "email_magic_link", Kind: "email", Enabled: true, Region: "global", SupportsRegistration: true, SupportsLogin: true, SupportsExplicitBinding: true},
		{Provider: "qq", Kind: "oauth2", Enabled: true, Region: "cn", SupportsRegistration: true, SupportsLogin: true, SupportsExplicitBinding: true, PKCERequired: true},
		{Provider: "wechat_open", Kind: "oauth2", Enabled: true, Region: "cn", SupportsRegistration: true, SupportsLogin: true, SupportsExplicitBinding: true, PKCERequired: true},
		{Provider: "google", Kind: "oidc", Enabled: true, Region: "global", SupportsRegistration: true, SupportsLogin: true, SupportsExplicitBinding: true, PKCERequired: true},
		{Provider: "microsoft_entra", Kind: "oidc", Enabled: true, Region: "global", SupportsRegistration: true, SupportsLogin: true, SupportsExplicitBinding: true, PKCERequired: true},
		{Provider: "github", Kind: "oauth2", Enabled: true, Region: "global", SupportsRegistration: true, SupportsLogin: true, SupportsExplicitBinding: true, PKCERequired: true},
		{Provider: "enterprise_oidc", Kind: "oidc", Enabled: true, Region: "enterprise", SupportsRegistration: false, SupportsLogin: true, SupportsExplicitBinding: true, PKCERequired: true},
		{Provider: "enterprise_saml", Kind: "saml", Enabled: true, Region: "enterprise", SupportsRegistration: false, SupportsLogin: true, SupportsExplicitBinding: true},
	}
}

func (service *IdentityService) BeginEmailRegistration(email, locale, region string) (IdentityChallenge, error) {
	normalized, err := normalizeIdentityEmail(email)
	if err != nil {
		return IdentityChallenge{}, err
	}
	service.mu.Lock()
	defer service.mu.Unlock()
	if _, exists := service.credentialBindings[credentialBindingKey("email_magic_link", normalized)]; exists {
		return IdentityChallenge{}, &IdentityError{Code: IdentityRegistrationConflict}
	}
	return service.newChallengeLocked("register", normalized, "", locale, region)
}

func (service *IdentityService) CompleteEmailRegistration(request CompleteRegistrationRequest) (CanonicalAccount, error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	record, err := service.consumeChallengeLocked(request.ChallengeID, request.Secret, "register")
	if err != nil {
		return CanonicalAccount{}, err
	}
	bindingKey := credentialBindingKey("email_magic_link", record.Email)
	if _, exists := service.credentialBindings[bindingKey]; exists {
		return CanonicalAccount{}, &IdentityError{Code: IdentityRegistrationConflict}
	}
	now := service.now().UTC()
	accountID := service.idLocked("account")
	account := CanonicalAccount{
		SchemaVersion: IdentitySchemaVersion,
		AccountID:     accountID,
		PrimaryEmail:  record.Email,
		DisplayName:   strings.TrimSpace(request.DisplayName),
		Locale:        preferredLocale(record.Email, record.Locale),
		Region:        preferredRegion(record.Email, record.Region),
		Status:        "active",
		CreatedAt:     now,
		UpdatedAt:     now,
	}
	credential := service.newCredentialLocked(accountID, "email_magic_link", record.Email, "", record.Email, "")
	service.accounts[accountID] = account
	service.credentials[credential.CredentialID] = credential
	service.credentialBindings[bindingKey] = accountID
	service.accountCredentials[accountID] = append(service.accountCredentials[accountID], credential.CredentialID)
	return account, nil
}

func (service *IdentityService) BeginEmailLogin(email string) (IdentityChallenge, error) {
	normalized, err := normalizeIdentityEmail(email)
	if err != nil {
		return IdentityChallenge{}, err
	}
	service.mu.Lock()
	defer service.mu.Unlock()
	accountID := service.credentialBindings[credentialBindingKey("email_magic_link", normalized)]
	return service.newChallengeLocked("login", normalized, accountID, "", "")
}

func (service *IdentityService) CompleteEmailLogin(challengeID, secret string) (LoginResult, error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	record, err := service.consumeChallengeLocked(challengeID, secret, "login")
	if err != nil || record.AccountID == "" {
		return LoginResult{}, &IdentityError{Code: IdentityInvalidProof}
	}
	return service.loginAccountLocked(record.AccountID)
}

// RegisterOAuthIdentity creates a new canonical account only for an explicit
// registration intent and only when the trusted provider adapter supplied a
// verified email. Existing email or provider bindings are conflicts, never
// implicit login/link/merge signals.
func (service *IdentityService) RegisterOAuthIdentity(
	identity OAuthProviderIdentity,
	displayName string,
	locale string,
	region string,
) (CanonicalAccount, error) {
	provider := strings.ToLower(strings.TrimSpace(identity.Provider))
	if !providerSupportsRegistration(provider) || strings.TrimSpace(identity.ProviderSubject) == "" {
		return CanonicalAccount{}, &IdentityError{Code: IdentityInvalidInput}
	}
	email, err := normalizeIdentityEmail(identity.VerifiedEmail)
	if err != nil {
		return CanonicalAccount{}, err
	}
	service.mu.Lock()
	defer service.mu.Unlock()
	emailBinding := credentialBindingKey("email_magic_link", email)
	providerBinding := credentialBindingKey(provider, identity.ProviderSubject)
	if _, exists := service.credentialBindings[emailBinding]; exists {
		return CanonicalAccount{}, &IdentityError{Code: IdentityRegistrationConflict}
	}
	if _, exists := service.credentialBindings[providerBinding]; exists {
		return CanonicalAccount{}, &IdentityError{Code: IdentityRegistrationConflict}
	}
	now := service.now().UTC()
	accountID := service.idLocked("account")
	account := CanonicalAccount{
		SchemaVersion: IdentitySchemaVersion,
		AccountID:     accountID,
		PrimaryEmail:  email,
		DisplayName:   strings.TrimSpace(displayName),
		Locale:        preferredLocale(email, locale),
		Region:        preferredRegion(email, region),
		Status:        "active",
		CreatedAt:     now,
		UpdatedAt:     now,
	}
	emailCredential := service.newCredentialLocked(accountID, "email_magic_link", email, "", email, "")
	providerCredential := service.newCredentialLocked(
		accountID,
		provider,
		identity.ProviderSubject,
		identity.ProviderUnionID,
		email,
		strings.TrimSpace(identity.VerifiedPhone),
	)
	service.accounts[accountID] = account
	service.credentials[emailCredential.CredentialID] = emailCredential
	service.credentials[providerCredential.CredentialID] = providerCredential
	service.credentialBindings[emailBinding] = accountID
	service.credentialBindings[providerBinding] = accountID
	service.accountCredentials[accountID] = append(
		service.accountCredentials[accountID],
		emailCredential.CredentialID,
		providerCredential.CredentialID,
	)
	return account, nil
}

// CompleteOAuthLogin authenticates only an already-bound provider subject.
// Verified email claims are intentionally ignored for account resolution.
func (service *IdentityService) CompleteOAuthLogin(identity OAuthProviderIdentity) (LoginResult, error) {
	provider := strings.ToLower(strings.TrimSpace(identity.Provider))
	subject := strings.TrimSpace(identity.ProviderSubject)
	if !providerSupportsLogin(provider) || subject == "" {
		return LoginResult{}, &IdentityError{Code: IdentityInvalidProof}
	}
	service.mu.Lock()
	defer service.mu.Unlock()
	accountID := service.credentialBindings[credentialBindingKey(provider, subject)]
	if accountID == "" {
		return LoginResult{}, &IdentityError{Code: IdentityInvalidProof}
	}
	now := service.now().UTC()
	for _, credentialID := range service.accountCredentials[accountID] {
		credential := service.credentials[credentialID]
		if credential.Provider == provider &&
			credential.ProviderSubjectFingerprint == fingerprintIdentityValue(subject) {
			credential.LastLoginAt = now
			service.credentials[credentialID] = credential
			break
		}
	}
	return service.loginAccountLocked(accountID)
}

func (service *IdentityService) loginAccountLocked(accountID string) (LoginResult, error) {
	account, exists := service.accounts[accountID]
	if !exists || account.Status != "active" {
		return LoginResult{}, &IdentityError{Code: IdentityInvalidProof}
	}
	if account.TwoFactor {
		challenge, challengeErr := service.newChallengeLocked("mfa", account.PrimaryEmail, account.AccountID, account.Locale, account.Region)
		if challengeErr != nil {
			return LoginResult{}, challengeErr
		}
		return LoginResult{
			SchemaVersion:     IdentitySchemaVersion,
			Status:            "mfa_required",
			AccountID:         account.AccountID,
			MFAChallengeID:    challenge.ChallengeID,
			ExpiresAt:         challenge.ExpiresAt,
			MFASecret:         challenge.Secret,
			MFADeliveryTarget: account.PrimaryEmail,
		}, nil
	}
	return service.newSessionLocked(account.AccountID)
}

func (service *IdentityService) CompleteMFA(challengeID, secret string) (LoginResult, error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	record, err := service.consumeChallengeLocked(challengeID, secret, "mfa")
	if err != nil || record.AccountID == "" {
		return LoginResult{}, &IdentityError{Code: IdentityInvalidProof}
	}
	account, exists := service.accounts[record.AccountID]
	if !exists || !account.TwoFactor || account.Status != "active" {
		return LoginResult{}, &IdentityError{Code: IdentityInvalidProof}
	}
	return service.newSessionLocked(account.AccountID)
}

func (service *IdentityService) BindCredential(accountID, actingAccountID string, request BindCredentialRequest) (IdentityCredential, error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	return service.bindCredentialLocked(accountID, actingAccountID, request)
}

func (service *IdentityService) bindCredentialLocked(accountID, actingAccountID string, request BindCredentialRequest) (IdentityCredential, error) {
	if !request.ExplicitConsent {
		return IdentityCredential{}, &IdentityError{Code: IdentityConsentRequired}
	}
	if !request.Reauthenticated || actingAccountID == "" || actingAccountID != accountID {
		return IdentityCredential{}, &IdentityError{Code: IdentityReauthRequired}
	}
	provider := strings.ToLower(strings.TrimSpace(request.Provider))
	if !providerSupportsBinding(provider) || strings.TrimSpace(request.ProviderSubject) == "" {
		return IdentityCredential{}, &IdentityError{Code: IdentityInvalidInput}
	}
	verifiedEmail := ""
	if request.VerifiedEmail != "" {
		normalized, err := normalizeIdentityEmail(request.VerifiedEmail)
		if err != nil {
			return IdentityCredential{}, err
		}
		verifiedEmail = normalized
	}
	if _, exists := service.accounts[accountID]; !exists {
		return IdentityCredential{}, &IdentityError{Code: IdentityNotFound}
	}
	bindingKey := credentialBindingKey(provider, request.ProviderSubject)
	if boundAccountID, exists := service.credentialBindings[bindingKey]; exists {
		if boundAccountID != accountID {
			return IdentityCredential{}, &IdentityError{Code: IdentityBindingConflict}
		}
		for _, credentialID := range service.accountCredentials[accountID] {
			credential := service.credentials[credentialID]
			if credential.Provider == provider && credential.ProviderSubjectFingerprint == fingerprintIdentityValue(request.ProviderSubject) {
				return credential, nil
			}
		}
	}
	credential := service.newCredentialLocked(
		accountID,
		provider,
		request.ProviderSubject,
		request.ProviderUnionID,
		verifiedEmail,
		strings.TrimSpace(request.VerifiedPhone),
	)
	service.credentials[credential.CredentialID] = credential
	service.credentialBindings[bindingKey] = accountID
	service.accountCredentials[accountID] = append(service.accountCredentials[accountID], credential.CredentialID)
	return credential, nil
}

// IssueCredentialBindingTicket is a trusted adapter boundary. OAuth/OIDC/SAML
// adapters call it only after validating the provider response. The A3-facing
// API consumes the opaque one-time ticket and never accepts raw provider
// subjects, union IDs, access tokens, or refresh tokens.
func (service *IdentityService) IssueCredentialBindingTicket(accountID string, request BindCredentialRequest) (IdentityBindingTicket, error) {
	provider := strings.ToLower(strings.TrimSpace(request.Provider))
	if strings.TrimSpace(accountID) == "" || !providerSupportsBinding(provider) || strings.TrimSpace(request.ProviderSubject) == "" {
		return IdentityBindingTicket{}, &IdentityError{Code: IdentityInvalidInput}
	}
	service.mu.Lock()
	defer service.mu.Unlock()
	if _, exists := service.accounts[accountID]; !exists {
		return IdentityBindingTicket{}, &IdentityError{Code: IdentityNotFound}
	}
	secret, err := service.secret()
	if err != nil {
		return IdentityBindingTicket{}, &IdentityError{Code: IdentityUnavailable}
	}
	keyID, key, ok := service.activeHashKeyLocked()
	if !ok {
		return IdentityBindingTicket{}, &IdentityError{Code: IdentityUnavailable}
	}
	now := service.now().UTC()
	ticketID := service.idLocked("binding_ticket")
	request.Provider = provider
	request.ExplicitConsent = false
	request.Reauthenticated = false
	service.bindingTickets[ticketID] = identityBindingTicketRecord{
		ID:              ticketID,
		AccountID:       accountID,
		Request:         request,
		SecretHash:      identityHMAC(key, secret),
		SecretHashKeyID: keyID,
		ExpiresAt:       now.Add(5 * time.Minute),
	}
	return IdentityBindingTicket{
		SchemaVersion: IdentitySchemaVersion,
		TicketID:      ticketID,
		Provider:      provider,
		ExpiresAt:     now.Add(5 * time.Minute),
		Secret:        secret,
	}, nil
}

func (service *IdentityService) BindCredentialWithTicket(accountID, actingAccountID, ticketID, secret string, explicitConsent, reauthenticated bool) (IdentityCredential, error) {
	if !explicitConsent {
		return IdentityCredential{}, &IdentityError{Code: IdentityConsentRequired}
	}
	if !reauthenticated {
		return IdentityCredential{}, &IdentityError{Code: IdentityReauthRequired}
	}
	service.mu.Lock()
	defer service.mu.Unlock()
	record, exists := service.bindingTickets[strings.TrimSpace(ticketID)]
	if !exists || record.Consumed || record.AccountID != accountID || !service.now().UTC().Before(record.ExpiresAt) {
		return IdentityCredential{}, &IdentityError{Code: IdentityInvalidProof}
	}
	key, exists := service.hashKeys[record.SecretHashKeyID]
	if !exists {
		return IdentityCredential{}, &IdentityError{Code: IdentityInvalidProof}
	}
	candidate := identityHMAC(key, secret)
	if !hmac.Equal(candidate[:], record.SecretHash[:]) {
		return IdentityCredential{}, &IdentityError{Code: IdentityInvalidProof}
	}
	record.Consumed = true
	service.bindingTickets[record.ID] = record
	request := record.Request
	request.ExplicitConsent = true
	request.Reauthenticated = true
	return service.bindCredentialLocked(accountID, actingAccountID, request)
}

func (service *IdentityService) EnableTwoFactor(accountID string, methods []string) (CanonicalAccount, error) {
	normalizedMethods, err := normalizeMFAMethods(methods)
	if err != nil {
		return CanonicalAccount{}, err
	}
	service.mu.Lock()
	defer service.mu.Unlock()
	account, exists := service.accounts[accountID]
	if !exists {
		return CanonicalAccount{}, &IdentityError{Code: IdentityNotFound}
	}
	account.TwoFactor = true
	account.TwoFactorMethods = normalizedMethods
	account.UpdatedAt = service.now().UTC()
	service.accounts[accountID] = account
	return account, nil
}

func (service *IdentityService) RevokeSession(sessionID string) {
	service.mu.Lock()
	defer service.mu.Unlock()
	record, exists := service.sessions[sessionID]
	if !exists {
		return
	}
	record.Revoked = true
	service.sessions[sessionID] = record
}

func (service *IdentityService) VerifySession(sessionID, token string) (string, bool) {
	service.mu.Lock()
	defer service.mu.Unlock()
	record, ok := service.verifySessionLocked(sessionID, token)
	if !ok {
		return "", false
	}
	return record.AccountID, true
}

func (service *IdentityService) VerifyFreshSession(sessionID, token string, maxAge time.Duration) (string, bool) {
	service.mu.Lock()
	defer service.mu.Unlock()
	record, ok := service.verifySessionLocked(sessionID, token)
	if !ok || maxAge <= 0 || service.now().UTC().Sub(record.AuthenticatedAt) > maxAge {
		return "", false
	}
	return record.AccountID, true
}

func (service *IdentityService) verifySessionLocked(sessionID, token string) (identitySessionRecord, bool) {
	record, exists := service.sessions[sessionID]
	if !exists || record.Revoked || !service.now().UTC().Before(record.ExpiresAt) {
		return identitySessionRecord{}, false
	}
	key, exists := service.hashKeys[record.TokenHashKeyID]
	if !exists {
		return identitySessionRecord{}, false
	}
	candidate := identityHMAC(key, token)
	if !hmac.Equal(candidate[:], record.TokenHash[:]) {
		return identitySessionRecord{}, false
	}
	return record, true
}

func (service *IdentityService) A3View(accountID string) (A3IdentityView, error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	account, exists := service.accounts[accountID]
	if !exists {
		return A3IdentityView{}, &IdentityError{Code: IdentityNotFound}
	}
	credentials := make([]A3CredentialView, 0, len(service.accountCredentials[accountID]))
	for _, credentialID := range service.accountCredentials[accountID] {
		credential := service.credentials[credentialID]
		credentials = append(credentials, A3CredentialView{Provider: credential.Provider, Kind: providerKind(credential.Provider)})
	}
	sort.Slice(credentials, func(i, j int) bool {
		if credentials[i].Provider == credentials[j].Provider {
			return credentials[i].Kind < credentials[j].Kind
		}
		return credentials[i].Provider < credentials[j].Provider
	})
	methods := append([]string(nil), account.TwoFactorMethods...)
	return A3IdentityView{
		SchemaVersion:               IdentitySchemaVersion,
		AccountID:                   account.AccountID,
		PrimaryEmailHint:            maskIdentityEmail(account.PrimaryEmail),
		DisplayName:                 account.DisplayName,
		Locale:                      account.Locale,
		Region:                      account.Region,
		Status:                      account.Status,
		PreferredRegistrationMethod: "email_magic_link",
		Credentials:                 credentials,
		TwoFactor: A3TwoFactorView{
			Enabled:     account.TwoFactor,
			Recommended: !account.TwoFactor,
			Methods:     methods,
		},
		ProviderCapabilities: IdentityProviderCapabilities(),
	}, nil
}

func (service *IdentityService) AccountCount() int {
	service.mu.Lock()
	defer service.mu.Unlock()
	return len(service.accounts)
}

func (service *IdentityService) newChallengeLocked(purpose, email, accountID, locale, region string) (IdentityChallenge, error) {
	secret, err := service.secret()
	if err != nil {
		return IdentityChallenge{}, &IdentityError{Code: IdentityUnavailable}
	}
	keyID, key, ok := service.activeHashKeyLocked()
	if !ok {
		return IdentityChallenge{}, &IdentityError{Code: IdentityUnavailable}
	}
	now := service.now().UTC()
	challengeID := service.idLocked("challenge")
	record := identityChallengeRecord{
		ID:              challengeID,
		Purpose:         purpose,
		Email:           email,
		Locale:          strings.TrimSpace(locale),
		Region:          strings.ToLower(strings.TrimSpace(region)),
		SecretHash:      identityHMAC(key, secret),
		SecretHashKeyID: keyID,
		ExpiresAt:       now.Add(10 * time.Minute),
		AccountID:       accountID,
	}
	service.challenges[challengeID] = record
	return IdentityChallenge{
		SchemaVersion:  IdentitySchemaVersion,
		ChallengeID:    challengeID,
		Purpose:        purpose,
		DeliveryMethod: "email",
		DeliveryHint:   maskIdentityEmail(email),
		ExpiresAt:      record.ExpiresAt,
		Secret:         secret,
	}, nil
}

func (service *IdentityService) consumeChallengeLocked(challengeID, secret, purpose string) (identityChallengeRecord, error) {
	record, exists := service.challenges[challengeID]
	if !exists || record.Consumed || record.Purpose != purpose || !service.now().UTC().Before(record.ExpiresAt) {
		return identityChallengeRecord{}, &IdentityError{Code: IdentityInvalidProof}
	}
	key, exists := service.hashKeys[record.SecretHashKeyID]
	if !exists {
		return identityChallengeRecord{}, &IdentityError{Code: IdentityInvalidProof}
	}
	candidate := identityHMAC(key, secret)
	if !hmac.Equal(candidate[:], record.SecretHash[:]) {
		return identityChallengeRecord{}, &IdentityError{Code: IdentityInvalidProof}
	}
	record.Consumed = true
	service.challenges[challengeID] = record
	return record, nil
}

func (service *IdentityService) newCredentialLocked(accountID, provider, subject, unionID, verifiedEmail, verifiedPhone string) IdentityCredential {
	return IdentityCredential{
		SchemaVersion:              IdentitySchemaVersion,
		CredentialID:               service.idLocked("credential"),
		AccountID:                  accountID,
		Provider:                   provider,
		ProviderSubjectFingerprint: fingerprintIdentityValue(subject),
		ProviderUnionFingerprint:   optionalFingerprint(unionID),
		VerifiedEmail:              verifiedEmail,
		VerifiedPhone:              verifiedPhone,
		CreatedAt:                  service.now().UTC(),
	}
}

func (service *IdentityService) newSessionLocked(accountID string) (LoginResult, error) {
	token, err := service.secret()
	if err != nil {
		return LoginResult{}, &IdentityError{Code: IdentityUnavailable}
	}
	keyID, key, ok := service.activeHashKeyLocked()
	if !ok {
		return LoginResult{}, &IdentityError{Code: IdentityUnavailable}
	}
	now := service.now().UTC()
	sessionID := service.idLocked("session")
	expiresAt := now.Add(24 * time.Hour)
	service.sessions[sessionID] = identitySessionRecord{
		ID:              sessionID,
		AccountID:       accountID,
		TokenHash:       identityHMAC(key, token),
		TokenHashKeyID:  keyID,
		AuthenticatedAt: now,
		ExpiresAt:       expiresAt,
	}
	return LoginResult{
		SchemaVersion: IdentitySchemaVersion,
		Status:        "authenticated",
		AccountID:     accountID,
		SessionID:     sessionID,
		ExpiresAt:     expiresAt,
		SessionToken:  token,
	}, nil
}

func (service *IdentityService) idLocked(prefix string) string {
	value := fmt.Sprintf("%s_%08d", prefix, service.nextID)
	service.nextID++
	return value
}

func (service *IdentityService) rotateHashKeyLocked(keyID string, key []byte) error {
	keyID = strings.TrimSpace(keyID)
	if keyID == "" || len(key) < 32 {
		return &IdentityError{Code: IdentityHashKeyInvalid}
	}
	if _, exists := service.hashKeys[keyID]; exists {
		return &IdentityError{Code: IdentityHashKeyInvalid}
	}
	service.hashKeys[keyID] = append([]byte(nil), key...)
	service.activeHashKeyID = keyID
	return nil
}

func (service *IdentityService) activeHashKeyLocked() (string, []byte, bool) {
	key, exists := service.hashKeys[service.activeHashKeyID]
	if !exists || service.activeHashKeyID == "" {
		return "", nil, false
	}
	return service.activeHashKeyID, key, true
}

func identityHMAC(key []byte, value string) [32]byte {
	mac := hmac.New(sha256.New, key)
	_, _ = mac.Write([]byte(value))
	var result [32]byte
	copy(result[:], mac.Sum(nil))
	return result
}

func normalizeIdentityEmail(value string) (string, error) {
	value = strings.TrimSpace(value)
	if strings.Count(value, "@") != 1 || strings.ContainsAny(value, "\r\n\t ") {
		return "", &IdentityError{Code: IdentityInvalidInput}
	}
	parts := strings.SplitN(value, "@", 2)
	if parts[0] == "" || parts[1] == "" || !strings.Contains(parts[1], ".") {
		return "", &IdentityError{Code: IdentityInvalidInput}
	}
	return parts[0] + "@" + strings.ToLower(parts[1]), nil
}

func maskIdentityEmail(value string) string {
	parts := strings.SplitN(value, "@", 2)
	if len(parts) != 2 || parts[0] == "" {
		return "***"
	}
	local := []rune(parts[0])
	if len(local) == 1 {
		return string(local[0]) + "***@" + parts[1]
	}
	return string(local[0]) + "***" + string(local[len(local)-1]) + "@" + parts[1]
}

func defaultLocale(email string) string {
	if isDomesticEmail(email) {
		return "zh-CN"
	}
	return "en"
}

func defaultRegion(email string) string {
	if isDomesticEmail(email) {
		return "cn"
	}
	return "global"
}

func preferredLocale(email, requested string) string {
	requested = strings.TrimSpace(requested)
	if requested != "" {
		return requested
	}
	return defaultLocale(email)
}

func preferredRegion(email, requested string) string {
	requested = strings.ToLower(strings.TrimSpace(requested))
	if requested != "" {
		return requested
	}
	return defaultRegion(email)
}

func isDomesticEmail(email string) bool {
	domain := strings.ToLower(strings.SplitN(email, "@", 2)[1])
	switch domain {
	case "qq.com", "foxmail.com", "163.com", "126.com", "yeah.net", "sina.com", "sina.cn", "sohu.com", "aliyun.com":
		return true
	default:
		return strings.HasSuffix(domain, ".cn")
	}
}

func providerSupportsBinding(provider string) bool {
	for _, capability := range IdentityProviderCapabilities() {
		if capability.Provider == provider {
			return capability.Enabled && capability.SupportsExplicitBinding
		}
	}
	return false
}

func providerSupportsRegistration(provider string) bool {
	for _, capability := range IdentityProviderCapabilities() {
		if capability.Provider == provider {
			return capability.Enabled &&
				capability.SupportsRegistration &&
				(capability.Kind == "oauth2" || capability.Kind == "oidc")
		}
	}
	return false
}

func providerSupportsLogin(provider string) bool {
	for _, capability := range IdentityProviderCapabilities() {
		if capability.Provider == provider {
			return capability.Enabled &&
				capability.SupportsLogin &&
				(capability.Kind == "oauth2" || capability.Kind == "oidc")
		}
	}
	return false
}

func providerKind(provider string) string {
	for _, capability := range IdentityProviderCapabilities() {
		if capability.Provider == provider {
			return capability.Kind
		}
	}
	return "unknown"
}

func credentialBindingKey(provider, subject string) string {
	return provider + ":" + fingerprintIdentityValue(subject)
}

func fingerprintIdentityValue(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}

func optionalFingerprint(value string) string {
	if strings.TrimSpace(value) == "" {
		return ""
	}
	return fingerprintIdentityValue(value)
}

func normalizeMFAMethods(methods []string) ([]string, error) {
	if len(methods) == 0 {
		return nil, &IdentityError{Code: IdentityInvalidInput}
	}
	allowed := map[string]struct{}{"totp": {}, "webauthn": {}, "sms": {}}
	seen := map[string]struct{}{}
	result := make([]string, 0, len(methods))
	for _, value := range methods {
		value = strings.ToLower(strings.TrimSpace(value))
		if _, ok := allowed[value]; !ok {
			return nil, &IdentityError{Code: IdentityInvalidInput}
		}
		if _, duplicate := seen[value]; duplicate {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	sort.Strings(result)
	return result, nil
}

func identitySecret() (string, error) {
	value := make([]byte, 32)
	if _, err := rand.Read(value); err != nil {
		return "", err
	}
	return hex.EncodeToString(value), nil
}

func identityHashKey() ([]byte, error) {
	value := make([]byte, 32)
	if _, err := rand.Read(value); err != nil {
		return nil, err
	}
	return value, nil
}
