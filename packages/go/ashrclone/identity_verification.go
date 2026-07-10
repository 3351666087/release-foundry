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

// IdentityVerificationIdentityStore is the identity mutation boundary used
// after a challenge is verified. Production implementations should return a
// transaction-scoped implementation from IdentityVerificationTransactionCoordinator.
type IdentityVerificationIdentityStore interface {
	GetAccount(context.Context, string) (IdentityAccountDTO, error)
	HasLoginCredential(context.Context, string, IdentityCredentialInput) (bool, error)
	CreateVerifiedAccount(context.Context, CreateIdentityAccountRequest) (IdentityAccountDTO, IdentityCredentialDTO, error)
	LinkVerifiedCredential(context.Context, string, LinkIdentityCredentialRequest) (IdentityCredentialDTO, bool, error)
	AuthenticateVerifiedCredential(context.Context, string, IdentityCredentialInput) (IdentityAuthenticationDTO, error)
}

type IdentityVerificationMutation func(
	IdentityVerificationIdentityStore,
	IdentityVerificationChallenge,
) (IdentityVerificationResultDTO, error)

// IdentityVerificationCompletionCommand carries only normalized values and
// keyed digests across the durable transaction boundary. Raw identifiers and
// verification codes must not be retained by a coordinator.
type IdentityVerificationCompletionCommand struct {
	ChallengeID         string
	CandidateCodeDigest string
	IdentifierDigest    string
	Channel             IdentityVerificationChannel
	CredentialKind      IdentityCredentialKind
	Purpose             IdentityVerificationPurpose
	TenantID            string
	AccountID           string
	ActorID             string
	DisplayName         string
	VerifiedAt          time.Time
	SessionExpiresAt    time.Time
	Verify              func(IdentityVerificationChallenge) error
	Mutate              IdentityVerificationMutation
}

// IdentityVerificationTransactionCoordinator owns the atomic boundary between
// consuming a verified receipt and applying its identity mutation.
type IdentityVerificationTransactionCoordinator interface {
	CompleteIdentityVerification(
		context.Context,
		IdentityVerificationCompletionCommand,
	) (IdentityVerificationResultDTO, error)
}

// ProductionIdentityVerificationStore marks a durable challenge store. It is
// intentionally capability based so HTTP/service code does not depend on a
// concrete PostgreSQL implementation.
type ProductionIdentityVerificationStore interface {
	IdentityVerificationStore
	IsProductionIdentityVerificationStore()
}

// ProductionIdentityVerificationTransactionCoordinator marks a coordinator
// that consumes a durable receipt and mutates identity in one database
// transaction.
type ProductionIdentityVerificationTransactionCoordinator interface {
	IdentityVerificationTransactionCoordinator
	IsProductionIdentityVerificationTransactionCoordinator()
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
	Store                  IdentityVerificationStore
	Sender                 IdentityVerificationSender
	Identity               *UnifiedIdentityService
	IdentityStore          IdentityVerificationIdentityStore
	TransactionCoordinator IdentityVerificationTransactionCoordinator
	ResponsePolicy         *IdentityVerificationResponsePolicy
	Now                    func() time.Time
	Random                 io.Reader
	DigestKey              []byte
	TTL                    time.Duration
	AttemptCap             int
	ResendCooldown         time.Duration
}

type IdentityVerificationService struct {
	store                  IdentityVerificationStore
	sender                 IdentityVerificationSender
	identity               IdentityVerificationIdentityStore
	transactionCoordinator IdentityVerificationTransactionCoordinator
	responsePolicy         *IdentityVerificationResponsePolicy
	now                    func() time.Time
	random                 io.Reader
	digestKey              []byte
	ttl                    time.Duration
	attemptCap             int
	resendCooldown         time.Duration

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
	identity := options.IdentityStore
	if identity == nil && options.Identity != nil {
		identity = unifiedIdentityVerificationStore{service: options.Identity}
	}
	coordinator := options.TransactionCoordinator
	_, productionStore := options.Store.(ProductionIdentityVerificationStore)
	_, productionCoordinator := coordinator.(ProductionIdentityVerificationTransactionCoordinator)
	if productionStore && !productionCoordinator {
		return nil, fmt.Errorf("production identity verification requires a postgres transaction coordinator")
	}
	if !productionStore && productionCoordinator {
		return nil, fmt.Errorf("production identity verification coordinator requires a production store")
	}
	if coordinator == nil {
		if identity == nil {
			return nil, fmt.Errorf("identity verification identity store is required")
		}
		coordinator = localIdentityVerificationTransactionCoordinator{
			store: options.Store, identity: identity,
		}
	} else if !productionCoordinator && identity == nil {
		return nil, fmt.Errorf("identity verification identity store is required")
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
		store: options.Store, sender: options.Sender, identity: identity,
		transactionCoordinator: coordinator,
		responsePolicy:         options.ResponsePolicy,
		now:                    options.Now, random: options.Random, digestKey: append([]byte(nil), options.DigestKey...),
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
	_, productionCoordinator := service.transactionCoordinator.(ProductionIdentityVerificationTransactionCoordinator)
	if purpose != IdentityVerificationBinding && !productionCoordinator {
		if accountID == "" {
			verificationErr := IdentityVerificationError{Code: "account_binding_required", Message: "login and recovery verification require account_id"}
			service.appendAudit("identity.verification.start", channel, purpose, tenantID, accountID, "rejected", verificationErr.Code, now)
			return IdentityVerificationChallengeDTO{}, verificationErr
		}
		hasCredential, accountErr := service.identity.HasLoginCredential(ctx, accountID, IdentityCredentialInput{
			Kind: kind, Provider: IdentityProviderLocal, Identifier: normalized, Verified: true,
		})
		if accountErr != nil || !hasCredential {
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
	verify := func(challenge IdentityVerificationChallenge) error {
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
	}
	mutate := func(identity IdentityVerificationIdentityStore, challenge IdentityVerificationChallenge) (IdentityVerificationResultDTO, error) {
		input := IdentityCredentialInput{Kind: kind, Provider: IdentityProviderLocal, Identifier: normalized, Verified: true}
		var account IdentityAccountDTO
		var credential IdentityCredentialDTO
		var created bool
		var mutationErr error
		switch purpose {
		case IdentityVerificationBinding:
			if accountID == "" {
				account, credential, mutationErr = identity.CreateVerifiedAccount(ctx, CreateIdentityAccountRequest{
					DisplayName: request.DisplayName, InitialCredential: &input,
				})
				created = mutationErr == nil
			} else {
				credential, created, mutationErr = identity.LinkVerifiedCredential(ctx, accountID, LinkIdentityCredentialRequest{
					Credential: input, ActorID: request.ActorID,
				})
				if mutationErr == nil {
					account, mutationErr = identity.GetAccount(ctx, accountID)
				}
			}
		case IdentityVerificationLogin, IdentityVerificationRecovery:
			var authenticated IdentityAuthenticationDTO
			authenticated, mutationErr = identity.AuthenticateVerifiedCredential(ctx, accountID, input)
			if mutationErr == nil {
				account, credential = authenticated.Account, authenticated.Credential
			}
		}
		if mutationErr != nil {
			return IdentityVerificationResultDTO{}, mutationErr
		}
		return IdentityVerificationResultDTO{
			SchemaVersion: IdentityVerificationSchemaVersion, ChallengeID: challenge.ChallengeID,
			Channel: channel, Purpose: purpose, TenantID: tenantID, Account: account,
			Credential: credential, Created: created, VerifiedAt: now,
		}, nil
	}
	command := IdentityVerificationCompletionCommand{
		ChallengeID:         challengeID,
		CandidateCodeDigest: service.digest("code", challengeID, code),
		IdentifierDigest:    service.digest("identifier", string(kind), normalized),
		Channel:             channel,
		CredentialKind:      kind,
		Purpose:             purpose,
		TenantID:            tenantID,
		AccountID:           accountID,
		ActorID:             strings.TrimSpace(request.ActorID),
		DisplayName:         strings.TrimSpace(request.DisplayName),
		VerifiedAt:          now,
		SessionExpiresAt:    now.Add(24 * time.Hour),
		Verify:              verify,
		Mutate:              mutate,
	}
	result, err := service.transactionCoordinator.CompleteIdentityVerification(ctx, command)
	if err != nil {
		service.appendAudit("identity.verification.complete", channel, purpose, tenantID, accountID, "rejected", verificationErrorCode(err), now)
		return IdentityVerificationResultDTO{}, err
	}
	service.appendAudit("identity.verification.complete", channel, purpose, tenantID, result.Account.AccountID, "success", "", now)
	return result, nil
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

type localIdentityVerificationTransactionCoordinator struct {
	store    IdentityVerificationStore
	identity IdentityVerificationIdentityStore
}

func (coordinator localIdentityVerificationTransactionCoordinator) CompleteIdentityVerification(
	ctx context.Context,
	command IdentityVerificationCompletionCommand,
) (IdentityVerificationResultDTO, error) {
	if command.Verify == nil || command.Mutate == nil {
		return IdentityVerificationResultDTO{}, fmt.Errorf("local identity verification completion callbacks are required")
	}
	var result IdentityVerificationResultDTO
	_, err := coordinator.store.ConsumeIdentityVerificationChallenge(ctx, command.ChallengeID, func(challenge IdentityVerificationChallenge) error {
		if err := command.Verify(challenge); err != nil {
			return err
		}
		var mutationErr error
		result, mutationErr = command.Mutate(coordinator.identity, challenge)
		return mutationErr
	})
	if err != nil {
		return IdentityVerificationResultDTO{}, err
	}
	return result, nil
}

type unifiedIdentityVerificationStore struct {
	service *UnifiedIdentityService
}

func (store unifiedIdentityVerificationStore) GetAccount(_ context.Context, accountID string) (IdentityAccountDTO, error) {
	return store.service.GetAccount(accountID)
}

func (store unifiedIdentityVerificationStore) HasLoginCredential(
	_ context.Context,
	accountID string,
	input IdentityCredentialInput,
) (bool, error) {
	account, err := store.service.GetAccount(accountID)
	if err != nil {
		return false, err
	}
	kind, provider, normalized, err := normalizeIdentityCredential(input)
	if err != nil {
		return false, err
	}
	store.service.mu.RLock()
	defer store.service.mu.RUnlock()
	digest := store.service.credentialDigest(kind, provider, normalized)
	credentialID, ok := store.service.credentialOwners[digest]
	if !ok {
		return false, nil
	}
	credential := store.service.credentials[credentialID]
	return credential != nil && credential.accountID == account.AccountID && credential.verified && credential.canLogin, nil
}

func (store unifiedIdentityVerificationStore) CreateVerifiedAccount(
	_ context.Context,
	request CreateIdentityAccountRequest,
) (IdentityAccountDTO, IdentityCredentialDTO, error) {
	account, err := store.service.CreateAccount(request)
	if err != nil {
		return IdentityAccountDTO{}, IdentityCredentialDTO{}, err
	}
	if len(account.Credentials) != 1 {
		return IdentityAccountDTO{}, IdentityCredentialDTO{}, fmt.Errorf("verified account creation did not return one credential")
	}
	return account, account.Credentials[0], nil
}

func (store unifiedIdentityVerificationStore) LinkVerifiedCredential(
	_ context.Context,
	accountID string,
	request LinkIdentityCredentialRequest,
) (IdentityCredentialDTO, bool, error) {
	return store.service.LinkCredentialWithStatus(accountID, request)
}

func (store unifiedIdentityVerificationStore) AuthenticateVerifiedCredential(
	_ context.Context,
	accountID string,
	input IdentityCredentialInput,
) (IdentityAuthenticationDTO, error) {
	authenticated, err := store.service.Authenticate(input)
	if err != nil {
		return IdentityAuthenticationDTO{}, err
	}
	if authenticated.Account.AccountID != accountID {
		return IdentityAuthenticationDTO{}, IdentityVerificationError{
			Code: "verification_account_mismatch", Message: "verified credential does not belong to the bound account",
		}
	}
	return authenticated, nil
}

var (
	_ IdentityVerificationIdentityStore          = unifiedIdentityVerificationStore{}
	_ IdentityVerificationTransactionCoordinator = localIdentityVerificationTransactionCoordinator{}
)
