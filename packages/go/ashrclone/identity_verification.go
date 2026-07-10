package ashrclone

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"strings"
	"sync"
	"time"
)

const IdentityVerificationSchemaVersion = "ashr.identity_verification.v1"

type IdentityVerificationPurpose string

const (
	IdentityVerificationBinding  IdentityVerificationPurpose = "binding"
	IdentityVerificationLogin    IdentityVerificationPurpose = "login"
	IdentityVerificationRecovery IdentityVerificationPurpose = "recovery"
)

type IdentityVerificationChannel string

const (
	IdentityVerificationEmail IdentityVerificationChannel = "email"
	IdentityVerificationPhone IdentityVerificationChannel = "phone"
)

var (
	ErrIdentityVerificationNotFound = errors.New("identity verification challenge not found")
	ErrIdentityVerificationConsumed = errors.New("identity verification challenge already consumed")
)

type IdentityVerificationError struct {
	Code    string
	Message string
}

func (err IdentityVerificationError) Error() string {
	if strings.TrimSpace(err.Message) != "" {
		return err.Message
	}
	return err.Code
}

type IdentityVerificationDelivery struct {
	ChallengeID string
	Channel     IdentityVerificationChannel
	Destination string
	Code        string
	Purpose     IdentityVerificationPurpose
	ExpiresAt   time.Time
}

type IdentityVerificationSender interface {
	SendIdentityVerification(context.Context, IdentityVerificationDelivery) error
}

type IdentityVerificationChallenge struct {
	ChallengeID      string
	Channel          IdentityVerificationChannel
	IdentifierDigest string
	CodeDigest       string
	Purpose          IdentityVerificationPurpose
	TenantID         string
	AccountID        string
	AttemptCount     int
	AttemptCap       int
	CreatedAt        time.Time
	ExpiresAt        time.Time
	ConsumedAt       *time.Time
}

type IdentityVerificationStore interface {
	CreateIdentityVerificationChallenge(context.Context, IdentityVerificationChallenge, time.Duration) error
	ConsumeIdentityVerificationChallenge(
		context.Context,
		string,
		func(IdentityVerificationChallenge) error,
	) (IdentityVerificationChallenge, error)
}

type IdentityVerificationAuditEvent struct {
	SchemaVersion string                      `json:"schema_version"`
	EventID       string                      `json:"event_id"`
	Action        string                      `json:"action"`
	Channel       IdentityVerificationChannel `json:"channel"`
	Purpose       IdentityVerificationPurpose `json:"purpose"`
	TenantID      string                      `json:"tenant_id"`
	AccountBound  bool                        `json:"account_bound"`
	Outcome       string                      `json:"outcome"`
	Reason        string                      `json:"reason,omitempty"`
	CreatedAt     time.Time                   `json:"created_at"`
}

type IdentityVerificationStartRequest struct {
	Channel    IdentityVerificationChannel
	Identifier string
	Purpose    IdentityVerificationPurpose
	TenantID   string
	AccountID  string
}

type IdentityVerificationChallengeDTO struct {
	SchemaVersion string                      `json:"schema_version"`
	ChallengeID   string                      `json:"challenge_id"`
	Channel       IdentityVerificationChannel `json:"channel"`
	Purpose       IdentityVerificationPurpose `json:"purpose"`
	TenantID      string                      `json:"tenant_id"`
	AccountBound  bool                        `json:"account_bound"`
	ExpiresAt     time.Time                   `json:"expires_at"`
	ResendAfter   time.Time                   `json:"resend_after"`
}

type IdentityVerificationCompleteRequest struct {
	ChallengeID string
	Code        string
	Channel     IdentityVerificationChannel
	Identifier  string
	Purpose     IdentityVerificationPurpose
	TenantID    string
	AccountID   string
	ActorID     string
	DisplayName string
}

type IdentityVerificationResultDTO struct {
	SchemaVersion string                      `json:"schema_version"`
	ChallengeID   string                      `json:"challenge_id"`
	Channel       IdentityVerificationChannel `json:"channel"`
	Purpose       IdentityVerificationPurpose `json:"purpose"`
	TenantID      string                      `json:"tenant_id"`
	Account       IdentityAccountDTO          `json:"account"`
	Credential    IdentityCredentialDTO       `json:"credential"`
	Created       bool                        `json:"credential_created"`
	VerifiedAt    time.Time                   `json:"verified_at"`
}

type IdentityVerificationServiceOptions struct {
	Store          IdentityVerificationStore
	Sender         IdentityVerificationSender
	Identity       *UnifiedIdentityService
	Now            func() time.Time
	Random         io.Reader
	DigestKey      []byte
	TTL            time.Duration
	AttemptCap     int
	ResendCooldown time.Duration
}

type IdentityVerificationService struct {
	store          IdentityVerificationStore
	sender         IdentityVerificationSender
	identity       *UnifiedIdentityService
	now            func() time.Time
	random         io.Reader
	digestKey      []byte
	ttl            time.Duration
	attemptCap     int
	resendCooldown time.Duration

	auditMu sync.RWMutex
	audit   []IdentityVerificationAuditEvent
}

func NewIdentityVerificationService(options IdentityVerificationServiceOptions) (*IdentityVerificationService, error) {
	if options.Store == nil {
		return nil, fmt.Errorf("identity verification store is required")
	}
	if options.Sender == nil {
		return nil, fmt.Errorf("identity verification sender is required")
	}
	if options.Identity == nil {
		return nil, fmt.Errorf("unified identity service is required")
	}
	if options.Now == nil {
		options.Now = time.Now
	}
	if options.Random == nil {
		options.Random = rand.Reader
	}
	if len(options.DigestKey) < 32 {
		return nil, fmt.Errorf("identity verification digest key must contain at least 32 bytes")
	}
	if options.TTL <= 0 {
		options.TTL = 10 * time.Minute
	}
	if options.AttemptCap <= 0 {
		options.AttemptCap = 5
	}
	if options.AttemptCap > 20 {
		return nil, fmt.Errorf("identity verification attempt cap must not exceed 20")
	}
	if options.ResendCooldown <= 0 {
		options.ResendCooldown = 60 * time.Second
	}
	if options.ResendCooldown >= options.TTL {
		return nil, fmt.Errorf("identity verification resend cooldown must be shorter than TTL")
	}
	return &IdentityVerificationService{
		store: options.Store, sender: options.Sender, identity: options.Identity,
		now: options.Now, random: options.Random, digestKey: append([]byte(nil), options.DigestKey...),
		ttl: options.TTL, attemptCap: options.AttemptCap, resendCooldown: options.ResendCooldown,
		audit: []IdentityVerificationAuditEvent{},
	}, nil
}

func (service *IdentityVerificationService) Start(
	ctx context.Context,
	request IdentityVerificationStartRequest,
) (IdentityVerificationChallengeDTO, error) {
	channel, kind, normalized, purpose, tenantID, accountID, err := normalizeVerificationRequest(
		request.Channel, request.Identifier, request.Purpose, request.TenantID, request.AccountID,
	)
	now := service.now().UTC()
	if err != nil {
		service.appendAudit("identity.verification.start", channel, purpose, tenantID, accountID, "rejected", verificationErrorCode(err), now)
		return IdentityVerificationChallengeDTO{}, err
	}
	if purpose != IdentityVerificationBinding {
		if accountID == "" {
			verificationErr := IdentityVerificationError{Code: "account_binding_required", Message: "login and recovery verification require account_id"}
			service.appendAudit("identity.verification.start", channel, purpose, tenantID, accountID, "rejected", verificationErr.Code, now)
			return IdentityVerificationChallengeDTO{}, verificationErr
		}
		account, accountErr := service.identity.GetAccount(accountID)
		if accountErr != nil || !accountHasCredential(service.identity, account, kind, normalized) {
			verificationErr := IdentityVerificationError{Code: "verification_target_unavailable", Message: "verification target is unavailable"}
			service.appendAudit("identity.verification.start", channel, purpose, tenantID, accountID, "rejected", verificationErr.Code, now)
			return IdentityVerificationChallengeDTO{}, verificationErr
		}
	}
	challengeID, err := service.newChallengeID()
	if err != nil {
		return IdentityVerificationChallengeDTO{}, err
	}
	code, err := service.newCode()
	if err != nil {
		return IdentityVerificationChallengeDTO{}, err
	}
	expiresAt := now.Add(service.ttl)
	challenge := IdentityVerificationChallenge{
		ChallengeID: challengeID, Channel: channel,
		IdentifierDigest: service.digest("identifier", string(kind), normalized),
		CodeDigest:       service.digest("code", challengeID, code),
		Purpose:          purpose, TenantID: tenantID, AccountID: accountID,
		AttemptCap: service.attemptCap, CreatedAt: now, ExpiresAt: expiresAt,
	}
	if err := service.store.CreateIdentityVerificationChallenge(ctx, challenge, service.resendCooldown); err != nil {
		service.appendAudit("identity.verification.start", channel, purpose, tenantID, accountID, "rejected", verificationErrorCode(err), now)
		return IdentityVerificationChallengeDTO{}, err
	}
	delivery := IdentityVerificationDelivery{
		ChallengeID: challengeID, Channel: channel, Destination: normalized,
		Code: code, Purpose: purpose, ExpiresAt: expiresAt,
	}
	if err := service.sender.SendIdentityVerification(ctx, delivery); err != nil {
		_, _ = service.store.ConsumeIdentityVerificationChallenge(ctx, challengeID, func(IdentityVerificationChallenge) error { return nil })
		service.appendAudit("identity.verification.start", channel, purpose, tenantID, accountID, "failed", "delivery_failed", now)
		return IdentityVerificationChallengeDTO{}, IdentityVerificationError{
			Code: "delivery_failed", Message: "identity verification delivery failed",
		}
	}
	service.appendAudit("identity.verification.start", channel, purpose, tenantID, accountID, "accepted", "", now)
	return IdentityVerificationChallengeDTO{
		SchemaVersion: IdentityVerificationSchemaVersion, ChallengeID: challengeID,
		Channel: channel, Purpose: purpose, TenantID: tenantID, AccountBound: accountID != "",
		ExpiresAt: expiresAt, ResendAfter: now.Add(service.resendCooldown),
	}, nil
}

func (service *IdentityVerificationService) Complete(
	ctx context.Context,
	request IdentityVerificationCompleteRequest,
) (IdentityVerificationResultDTO, error) {
	channel, kind, normalized, purpose, tenantID, accountID, err := normalizeVerificationRequest(
		request.Channel, request.Identifier, request.Purpose, request.TenantID, request.AccountID,
	)
	now := service.now().UTC()
	if err != nil {
		return IdentityVerificationResultDTO{}, err
	}
	challengeID := strings.TrimSpace(request.ChallengeID)
	code := strings.TrimSpace(request.Code)
	if challengeID == "" || code == "" || len(code) > 32 {
		return IdentityVerificationResultDTO{}, IdentityVerificationError{Code: "invalid_verification_proof", Message: "verification proof is invalid"}
	}
	challenge, err := service.store.ConsumeIdentityVerificationChallenge(ctx, challengeID, func(challenge IdentityVerificationChallenge) error {
		switch {
		case challenge.Channel != channel || challenge.Purpose != purpose ||
			challenge.TenantID != tenantID || challenge.AccountID != accountID:
			return IdentityVerificationError{Code: "verification_scope_mismatch", Message: "verification challenge scope does not match"}
		case !hmac.Equal(
			[]byte(challenge.IdentifierDigest),
			[]byte(service.digest("identifier", string(kind), normalized)),
		):
			return IdentityVerificationError{Code: "verification_scope_mismatch", Message: "verification challenge scope does not match"}
		case !hmac.Equal([]byte(challenge.CodeDigest), []byte(service.digest("code", challengeID, code))):
			return IdentityVerificationError{Code: "verification_code_invalid", Message: "verification code is invalid"}
		default:
			return nil
		}
	})
	if err != nil {
		service.appendAudit("identity.verification.complete", channel, purpose, tenantID, accountID, "rejected", verificationErrorCode(err), now)
		return IdentityVerificationResultDTO{}, err
	}

	var account IdentityAccountDTO
	var credential IdentityCredentialDTO
	var created bool
	input := IdentityCredentialInput{Kind: kind, Provider: IdentityProviderLocal, Identifier: normalized, Verified: true}
	switch purpose {
	case IdentityVerificationBinding:
		if accountID == "" {
			account, err = service.identity.CreateAccount(CreateIdentityAccountRequest{
				DisplayName: request.DisplayName, InitialCredential: &input,
			})
			if err == nil {
				credential = account.Credentials[0]
				created = true
			}
		} else {
			credential, created, err = service.identity.LinkCredentialWithStatus(accountID, LinkIdentityCredentialRequest{
				Credential: input, ActorID: request.ActorID,
			})
			if err == nil {
				account, err = service.identity.GetAccount(accountID)
			}
		}
	case IdentityVerificationLogin, IdentityVerificationRecovery:
		var authenticated IdentityAuthenticationDTO
		authenticated, err = service.identity.Authenticate(input)
		if err == nil && authenticated.Account.AccountID != accountID {
			err = IdentityVerificationError{Code: "verification_account_mismatch", Message: "verified credential does not belong to the bound account"}
		} else if err == nil {
			account, credential = authenticated.Account, authenticated.Credential
		}
	}
	if err != nil {
		service.appendAudit("identity.verification.complete", channel, purpose, tenantID, accountID, "rejected", verificationErrorCode(err), now)
		return IdentityVerificationResultDTO{}, err
	}
	service.appendAudit("identity.verification.complete", channel, purpose, tenantID, account.AccountID, "success", "", now)
	return IdentityVerificationResultDTO{
		SchemaVersion: IdentityVerificationSchemaVersion, ChallengeID: challenge.ChallengeID,
		Channel: channel, Purpose: purpose, TenantID: tenantID, Account: account,
		Credential: credential, Created: created, VerifiedAt: now,
	}, nil
}

func (service *IdentityVerificationService) AuditEvents() []IdentityVerificationAuditEvent {
	service.auditMu.RLock()
	defer service.auditMu.RUnlock()
	return append([]IdentityVerificationAuditEvent(nil), service.audit...)
}

func (service *IdentityVerificationService) Close() {
	for index := range service.digestKey {
		service.digestKey[index] = 0
	}
}

func (service *IdentityVerificationService) appendAudit(
	action string,
	channel IdentityVerificationChannel,
	purpose IdentityVerificationPurpose,
	tenantID, accountID, outcome, reason string,
	now time.Time,
) {
	eventID, err := service.newChallengeID()
	if err != nil {
		eventID = "audit_unavailable"
	}
	event := IdentityVerificationAuditEvent{
		SchemaVersion: IdentityVerificationSchemaVersion, EventID: eventID,
		Action: action, Channel: channel, Purpose: purpose, TenantID: tenantID,
		AccountBound: strings.TrimSpace(accountID) != "", Outcome: outcome, Reason: reason, CreatedAt: now,
	}
	service.auditMu.Lock()
	service.audit = append(service.audit, event)
	service.auditMu.Unlock()
}

func (service *IdentityVerificationService) digest(parts ...string) string {
	mac := hmac.New(sha256.New, service.digestKey)
	for _, part := range parts {
		_, _ = mac.Write([]byte(part))
		_, _ = mac.Write([]byte{0})
	}
	return hex.EncodeToString(mac.Sum(nil))
}

func (service *IdentityVerificationService) newChallengeID() (string, error) {
	raw := make([]byte, 18)
	if _, err := io.ReadFull(service.random, raw); err != nil {
		return "", fmt.Errorf("generate identity verification id: %w", err)
	}
	return "ivc_" + hex.EncodeToString(raw), nil
}

func (service *IdentityVerificationService) newCode() (string, error) {
	raw := make([]byte, 4)
	if _, err := io.ReadFull(service.random, raw); err != nil {
		return "", fmt.Errorf("generate identity verification code: %w", err)
	}
	value := uint32(raw[0])<<24 | uint32(raw[1])<<16 | uint32(raw[2])<<8 | uint32(raw[3])
	return fmt.Sprintf("%06d", value%1000000), nil
}

func normalizeVerificationRequest(
	channel IdentityVerificationChannel,
	identifier string,
	purpose IdentityVerificationPurpose,
	tenantID, accountID string,
) (IdentityVerificationChannel, IdentityCredentialKind, string, IdentityVerificationPurpose, string, string, error) {
	channel = IdentityVerificationChannel(strings.ToLower(strings.TrimSpace(string(channel))))
	purpose = IdentityVerificationPurpose(strings.ToLower(strings.TrimSpace(string(purpose))))
	tenantID = strings.TrimSpace(tenantID)
	accountID = strings.TrimSpace(accountID)
	if tenantID == "" || len(tenantID) > 256 || strings.ContainsAny(tenantID, " \t\r\n/") {
		return channel, "", "", purpose, tenantID, accountID,
			IdentityVerificationError{Code: "invalid_tenant", Message: "tenant_id is required and must be a canonical handle"}
	}
	switch purpose {
	case IdentityVerificationBinding, IdentityVerificationLogin, IdentityVerificationRecovery:
	default:
		return channel, "", "", purpose, tenantID, accountID,
			IdentityVerificationError{Code: "invalid_verification_purpose", Message: "purpose must be binding, login, or recovery"}
	}
	var kind IdentityCredentialKind
	switch channel {
	case IdentityVerificationEmail:
		kind = IdentityCredentialEmail
	case IdentityVerificationPhone:
		kind = IdentityCredentialPhone
	default:
		return channel, "", "", purpose, tenantID, accountID,
			IdentityVerificationError{Code: "invalid_verification_channel", Message: "channel must be email or phone"}
	}
	_, _, normalized, err := normalizeIdentityCredential(IdentityCredentialInput{
		Kind: kind, Provider: IdentityProviderLocal, Identifier: identifier,
	})
	if err != nil {
		return channel, "", "", purpose, tenantID, accountID, err
	}
	return channel, kind, normalized, purpose, tenantID, accountID, nil
}

func accountHasCredential(
	identity *UnifiedIdentityService,
	account IdentityAccountDTO,
	kind IdentityCredentialKind,
	normalized string,
) bool {
	identity.mu.RLock()
	defer identity.mu.RUnlock()
	digest := identity.credentialDigest(kind, IdentityProviderLocal, normalized)
	credentialID, ok := identity.credentialOwners[digest]
	if !ok {
		return false
	}
	credential := identity.credentials[credentialID]
	return credential != nil && credential.accountID == account.AccountID && credential.verified && credential.canLogin
}

func verificationErrorCode(err error) string {
	var verification IdentityVerificationError
	var identity IdentityDomainError
	switch {
	case errors.As(err, &verification):
		return verification.Code
	case errors.As(err, &identity):
		return identity.Code
	case errors.Is(err, ErrIdentityVerificationNotFound):
		return "verification_not_found"
	case errors.Is(err, ErrIdentityVerificationConsumed):
		return "verification_consumed"
	default:
		return "verification_failed"
	}
}
