package ashrclone

import (
	"context"
	"errors"
	"strings"
	"time"
)

const IdentitySecurityServiceSchemaVersion = "ashr.identity_security_service.v1"

type IdentitySecurityBeginRequest struct {
	Operation      string
	IdempotencyKey string
	Password       string
}

type IdentitySecurityBeginResult struct {
	SchemaVersion            string `json:"schema_version"`
	Operation                string `json:"operation"`
	PasswordStatus           string `json:"password_status,omitempty"`
	TwoFactorStatus          string `json:"two_factor_status,omitempty"`
	TwoFactorOptional        bool   `json:"two_factor_optional"`
	TwoFactorRecommended     bool   `json:"two_factor_recommended"`
	ConfirmationRequired     bool   `json:"confirmation_required,omitempty"`
	ConfirmationChallengeID  string `json:"confirmation_challenge_id,omitempty"`
	ProvisioningURI          string `json:"provisioning_uri,omitempty"`
	SecurityVersion          int64  `json:"security_version"`
	SessionsRevoked          int64  `json:"sessions_revoked"`
	ReauthenticationRequired bool   `json:"reauthentication_required,omitempty"`
}

type IdentitySecurityConfirmRequest struct {
	IdempotencyKey string
	ChallengeID    string
	Code           string
}

type IdentitySecurityConfirmResult struct {
	SchemaVersion            string   `json:"schema_version"`
	Operation                string   `json:"operation"`
	TwoFactorStatus          string   `json:"two_factor_status"`
	TwoFactorOptional        bool     `json:"two_factor_optional"`
	TwoFactorRecommended     bool     `json:"two_factor_recommended"`
	RecoveryCodes            []string `json:"recovery_codes"`
	RecoveryCodesRemaining   int      `json:"recovery_codes_remaining"`
	SecurityVersion          int64    `json:"security_version"`
	SessionsRevoked          int64    `json:"sessions_revoked"`
	ReauthenticationRequired bool     `json:"reauthentication_required"`
}

type IdentitySecurityServiceOptions struct {
	Processor      IdentitySecuritySecretProcessor
	TicketIssuer   IdentitySecurityTicketIssuer
	MutationStore  IdentitySecurityHTTPStore
	OrganizationID string
	ProjectID      string
	TicketTTL      time.Duration
	Now            func() time.Time
}

// IdentitySecurityService coordinates secret processing, scoped ticket
// issuance and the existing atomic PostgreSQL mutation. It never returns
// internal refs, digests, receipts or ticket identifiers to an HTTP caller.
type IdentitySecurityService struct {
	processor      IdentitySecuritySecretProcessor
	ticketIssuer   IdentitySecurityTicketIssuer
	mutationStore  IdentitySecurityHTTPStore
	organizationID string
	projectID      string
	ticketTTL      time.Duration
	now            func() time.Time
}

func NewIdentitySecurityService(
	options IdentitySecurityServiceOptions,
) (*IdentitySecurityService, error) {
	if options.Processor == nil || options.TicketIssuer == nil ||
		options.MutationStore == nil {
		return nil, errors.New("identity security service dependencies are required")
	}
	options.OrganizationID = strings.TrimSpace(options.OrganizationID)
	options.ProjectID = strings.TrimSpace(options.ProjectID)
	if !validPostgresIdentityVerificationUUID(options.OrganizationID) ||
		!validPostgresIdentityVerificationUUID(options.ProjectID) {
		return nil, errors.New("identity security service scope must use canonical UUIDs")
	}
	if options.TicketTTL <= 0 {
		options.TicketTTL = 5 * time.Minute
	}
	if options.TicketTTL < time.Second || options.TicketTTL > 5*time.Minute {
		return nil, errors.New("identity security service ticket TTL must be between 1s and 5m")
	}
	if options.Now == nil {
		options.Now = time.Now
	}
	return &IdentitySecurityService{
		processor:      options.Processor,
		ticketIssuer:   options.TicketIssuer,
		mutationStore:  options.MutationStore,
		organizationID: options.OrganizationID,
		projectID:      options.ProjectID,
		ticketTTL:      options.TicketTTL,
		now:            options.Now,
	}, nil
}

func (service *IdentitySecurityService) Begin(
	ctx context.Context,
	session IdentityHTTPSession,
	request IdentitySecurityBeginRequest,
) (IdentitySecurityBeginResult, error) {
	session = normalizeIdentitySecuritySession(session)
	request.Operation = strings.TrimSpace(request.Operation)
	request.IdempotencyKey = strings.TrimSpace(request.IdempotencyKey)
	if ctx == nil || !service.validSession(session) ||
		!validIdentitySecurityIdempotencyKey(request.IdempotencyKey) {
		return IdentitySecurityBeginResult{}, ErrIdentitySecurityRejected
	}
	switch request.Operation {
	case "password_enroll", "password_change", "password_recovery":
		if !validIdentitySecurityPassword(request.Password) {
			return IdentitySecurityBeginResult{}, ErrIdentitySecurityRejected
		}
	case "mfa_enroll":
		if request.Password != "" {
			return IdentitySecurityBeginResult{}, ErrIdentitySecurityRejected
		}
	default:
		return IdentitySecurityBeginResult{}, ErrIdentitySecurityRejected
	}

	processed, err := service.processor.ProcessIdentitySecuritySecret(
		ctx,
		IdentitySecuritySecretProcessRequest{
			AccountID:      session.AccountID,
			Operation:      request.Operation,
			IdempotencyKey: request.IdempotencyKey,
			Password:       request.Password,
		},
	)
	request.Password = ""
	if err != nil {
		return IdentitySecurityBeginResult{}, identitySecurityProcessorServiceError(err)
	}
	if !validIdentitySecuritySecretProcessResult(request.Operation, processed) {
		service.cleanup(
			ctx,
			session.AccountID,
			request.Operation,
			request.IdempotencyKey,
			processed.CleanupToken,
		)
		return IdentitySecurityBeginResult{}, ErrIdentitySecurityUnavailable
	}
	issueRequest := service.issueRequest(
		session,
		request.Operation,
		request.IdempotencyKey,
		processed.SecretRef,
		processed.SecretDigest,
		"",
		0,
	)
	issued, err := service.ticketIssuer.IssueIdentitySecurityMutationTicket(
		ctx,
		issueRequest,
	)
	if err != nil {
		service.cleanup(
			ctx,
			session.AccountID,
			request.Operation,
			request.IdempotencyKey,
			processed.CleanupToken,
		)
		return IdentitySecurityBeginResult{}, identitySecurityServiceError(err)
	}
	if !validIdentitySecurityIssuedTicket(
		issueRequest,
		issued,
		service.now().UTC(),
	) {
		service.cleanup(
			ctx,
			session.AccountID,
			request.Operation,
			request.IdempotencyKey,
			processed.CleanupToken,
		)
		return IdentitySecurityBeginResult{}, ErrIdentitySecurityUnavailable
	}
	mutationResult, err := service.mutationStore.MutateIdentitySecurity(
		ctx,
		identitySecurityMutationFromIssue(session, issueRequest, issued),
	)
	if err != nil ||
		!validIdentitySecurityMutationResult(request.Operation, mutationResult) {
		_ = service.ticketIssuer.CancelIdentitySecurityMutationTicket(
			ctx,
			issueRequest,
			issued,
		)
		service.cleanup(
			ctx,
			session.AccountID,
			request.Operation,
			request.IdempotencyKey,
			processed.CleanupToken,
		)
		return IdentitySecurityBeginResult{}, identitySecurityServiceError(err)
	}
	result := IdentitySecurityBeginResult{
		SchemaVersion:            IdentitySecurityServiceSchemaVersion,
		Operation:                request.Operation,
		PasswordStatus:           mutationResult.PasswordStatus,
		TwoFactorStatus:          mutationResult.TwoFactorStatus,
		TwoFactorOptional:        true,
		TwoFactorRecommended:     true,
		ConfirmationRequired:     mutationResult.ConfirmationRequired,
		ConfirmationChallengeID:  processed.ConfirmationChallengeID,
		SecurityVersion:          mutationResult.SecurityVersion,
		SessionsRevoked:          mutationResult.SessionsRevoked,
		ReauthenticationRequired: mutationResult.ReauthenticationRequired,
	}
	if request.Operation != "mfa_enroll" {
		return result, nil
	}
	handoff, err := service.processor.ConsumeIdentitySecuritySecretHandoff(
		ctx,
		IdentitySecuritySecretHandoffRequest{
			AccountID:      session.AccountID,
			Operation:      request.Operation,
			IdempotencyKey: request.IdempotencyKey,
			HandoffID:      processed.HandoffID,
		},
	)
	if err != nil {
		return IdentitySecurityBeginResult{}, identitySecurityProcessorServiceError(err)
	}
	if !validIdentitySecuritySecretHandoff(request.Operation, handoff) {
		return IdentitySecurityBeginResult{}, ErrIdentitySecurityUnavailable
	}
	result.ProvisioningURI = handoff.ProvisioningURI
	return result, nil
}

func (service *IdentitySecurityService) Confirm(
	ctx context.Context,
	session IdentityHTTPSession,
	request IdentitySecurityConfirmRequest,
) (IdentitySecurityConfirmResult, error) {
	session = normalizeIdentitySecuritySession(session)
	request.IdempotencyKey = strings.TrimSpace(request.IdempotencyKey)
	request.ChallengeID = strings.TrimSpace(request.ChallengeID)
	request.Code = strings.TrimSpace(request.Code)
	if ctx == nil || !service.validSession(session) ||
		!validIdentitySecuritySecretConfirmRequest(
			IdentitySecuritySecretConfirmRequest{
				AccountID:      session.AccountID,
				ChallengeID:    request.ChallengeID,
				Code:           request.Code,
				IdempotencyKey: request.IdempotencyKey,
			},
		) {
		return IdentitySecurityConfirmResult{}, ErrIdentitySecurityRejected
	}
	processed, err := service.processor.ConfirmIdentitySecuritySecret(
		ctx,
		IdentitySecuritySecretConfirmRequest{
			AccountID:      session.AccountID,
			ChallengeID:    request.ChallengeID,
			Code:           request.Code,
			IdempotencyKey: request.IdempotencyKey,
		},
	)
	request.Code = ""
	if err != nil {
		return IdentitySecurityConfirmResult{}, identitySecurityProcessorServiceError(err)
	}
	if !validIdentitySecuritySecretConfirmResult(processed) {
		service.cleanup(
			ctx,
			session.AccountID,
			"mfa_confirm",
			request.IdempotencyKey,
			processed.CleanupToken,
		)
		return IdentitySecurityConfirmResult{}, ErrIdentitySecurityUnavailable
	}
	issueRequest := service.issueRequest(
		session,
		"mfa_confirm",
		request.IdempotencyKey,
		"",
		"",
		processed.RecoveryBatchDigest,
		processed.RecoveryCodeCount,
	)
	issued, err := service.ticketIssuer.IssueIdentitySecurityMutationTicket(
		ctx,
		issueRequest,
	)
	if err != nil {
		service.cleanup(
			ctx,
			session.AccountID,
			"mfa_confirm",
			request.IdempotencyKey,
			processed.CleanupToken,
		)
		return IdentitySecurityConfirmResult{}, identitySecurityServiceError(err)
	}
	if !validIdentitySecurityIssuedTicket(
		issueRequest,
		issued,
		service.now().UTC(),
	) {
		service.cleanup(
			ctx,
			session.AccountID,
			"mfa_confirm",
			request.IdempotencyKey,
			processed.CleanupToken,
		)
		return IdentitySecurityConfirmResult{}, ErrIdentitySecurityUnavailable
	}
	mutationResult, err := service.mutationStore.MutateIdentitySecurity(
		ctx,
		identitySecurityMutationFromIssue(session, issueRequest, issued),
	)
	if err != nil ||
		!validIdentitySecurityMutationResult("mfa_confirm", mutationResult) {
		_ = service.ticketIssuer.CancelIdentitySecurityMutationTicket(
			ctx,
			issueRequest,
			issued,
		)
		service.cleanup(
			ctx,
			session.AccountID,
			"mfa_confirm",
			request.IdempotencyKey,
			processed.CleanupToken,
		)
		return IdentitySecurityConfirmResult{}, identitySecurityServiceError(err)
	}
	handoff, err := service.processor.ConsumeIdentitySecuritySecretHandoff(
		ctx,
		IdentitySecuritySecretHandoffRequest{
			AccountID:      session.AccountID,
			Operation:      "mfa_confirm",
			IdempotencyKey: request.IdempotencyKey,
			HandoffID:      processed.HandoffID,
		},
	)
	if err != nil {
		return IdentitySecurityConfirmResult{}, identitySecurityProcessorServiceError(err)
	}
	if !validIdentitySecuritySecretHandoff("mfa_confirm", handoff) {
		return IdentitySecurityConfirmResult{}, ErrIdentitySecurityUnavailable
	}
	return IdentitySecurityConfirmResult{
		SchemaVersion:            IdentitySecurityServiceSchemaVersion,
		Operation:                "mfa_confirm",
		TwoFactorStatus:          mutationResult.TwoFactorStatus,
		TwoFactorOptional:        true,
		TwoFactorRecommended:     true,
		RecoveryCodes:            append([]string(nil), handoff.RecoveryCodes...),
		RecoveryCodesRemaining:   mutationResult.RecoveryCodesRemaining,
		SecurityVersion:          mutationResult.SecurityVersion,
		SessionsRevoked:          mutationResult.SessionsRevoked,
		ReauthenticationRequired: mutationResult.ReauthenticationRequired,
	}, nil
}

func (service *IdentitySecurityService) issueRequest(
	session IdentityHTTPSession,
	operation string,
	idempotencyKey string,
	secretRef string,
	secretDigest string,
	recoveryBatchDigest string,
	recoveryCodeCount int,
) IdentitySecurityTicketIssueRequest {
	request := IdentitySecurityTicketIssueRequest{
		OrganizationID:      service.organizationID,
		ProjectID:           service.projectID,
		AccountID:           session.AccountID,
		ActorID:             session.ActorID,
		SessionID:           session.SessionID,
		SessionDigest:       session.SessionDigest,
		Operation:           operation,
		IdempotencyKey:      idempotencyKey,
		SecretRef:           secretRef,
		SecretDigest:        secretDigest,
		RecoveryBatchDigest: recoveryBatchDigest,
		RecoveryCodeCount:   recoveryCodeCount,
		ExpiresAt:           service.now().UTC().Add(service.ticketTTL),
	}
	request.ContextDigest = identitySecurityTicketContextDigest(request)
	return request
}

func (service *IdentitySecurityService) validSession(
	session IdentityHTTPSession,
) bool {
	return service != nil && service.processor != nil &&
		service.ticketIssuer != nil && service.mutationStore != nil &&
		!session.Revoked &&
		validPostgresIdentityVerificationUUID(session.AccountID) &&
		session.ActorID == session.AccountID &&
		validPostgresIdentityVerificationUUID(session.SessionID) &&
		validIdentitySecurityDigest(session.SessionDigest)
}

func (service *IdentitySecurityService) cleanup(
	ctx context.Context,
	accountID string,
	operation string,
	idempotencyKey string,
	cleanupToken string,
) {
	request := IdentitySecuritySecretCleanupRequest{
		AccountID:      accountID,
		Operation:      operation,
		IdempotencyKey: idempotencyKey,
		CleanupToken:   cleanupToken,
	}
	if ctx == nil || !validIdentitySecuritySecretCleanupRequest(request) {
		return
	}
	_ = service.processor.CleanupIdentitySecuritySecret(ctx, request)
}

func identitySecurityMutationFromIssue(
	session IdentityHTTPSession,
	request IdentitySecurityTicketIssueRequest,
	issued IdentitySecurityIssuedTicket,
) IdentitySecurityMutation {
	return IdentitySecurityMutation{
		AccountID:      session.AccountID,
		ActorID:        session.ActorID,
		SessionID:      session.SessionID,
		Operation:      request.Operation,
		IdempotencyKey: request.IdempotencyKey,
		Ticket: IdentitySecurityMutationTicket{
			TicketID:      issued.TicketID,
			AccountID:     session.AccountID,
			Operation:     request.Operation,
			ReceiptDigest: issued.ReceiptID,
			ContextDigest: issued.ContextDigest,
			ExpiresAt:     issued.ExpiresAt,
		},
	}
}

func normalizeIdentitySecuritySession(
	session IdentityHTTPSession,
) IdentityHTTPSession {
	session.AccountID = strings.TrimSpace(session.AccountID)
	session.ActorID = strings.TrimSpace(session.ActorID)
	session.SessionID = strings.TrimSpace(session.SessionID)
	session.SessionDigest = strings.TrimSpace(session.SessionDigest)
	return session
}

func identitySecurityProcessorServiceError(err error) error {
	if errors.Is(err, ErrIdentitySecurityProcessorRejected) {
		return ErrIdentitySecurityRejected
	}
	return ErrIdentitySecurityUnavailable
}

func identitySecurityServiceError(err error) error {
	if errors.Is(err, ErrIdentitySecurityRejected) {
		return ErrIdentitySecurityRejected
	}
	return ErrIdentitySecurityUnavailable
}

func validIdentitySecurityIssuedTicket(
	request IdentitySecurityTicketIssueRequest,
	issued IdentitySecurityIssuedTicket,
	now time.Time,
) bool {
	return issued.TicketID == strings.TrimSpace(issued.TicketID) &&
		issued.ReceiptID == strings.TrimSpace(issued.ReceiptID) &&
		issued.ContextDigest == request.ContextDigest &&
		validIdentitySecurityDigest(issued.TicketID) &&
		validIdentitySecurityDigest(issued.ReceiptID) &&
		!now.IsZero() &&
		!issued.ExpiresAt.IsZero() &&
		issued.ExpiresAt.After(now) &&
		!issued.ExpiresAt.After(request.ExpiresAt)
}
