package ashrclone

import (
	"context"
	"strings"
	"time"
)

const IdentityCredentialLinkSchemaVersion = "ashr.identity_credential_link.v1"

// IdentityCredentialLinkCommand is the complete trusted input crossing the
// credential-link transaction boundary. It deliberately contains no raw
// identifier, OAuth token/code, password, OTP, caller-controlled verified
// flag, credential ID, or actor override.
type IdentityCredentialLinkCommand struct {
	AccountID        string
	ActorID          string
	SessionID        string
	SessionDigest    string
	Provider         IdentityProvider
	TenantID         string
	ProjectID        string
	ProofReceiptID   string
	MutationTicketID string
	StepUpReceiptID  string
	IdempotencyKey   string
}

// IdentityCredentialLinkResultDTO is intentionally public-safe. Authorization
// receipts, session digests, and provider subjects cannot be represented in
// this response type.
type IdentityCredentialLinkResultDTO struct {
	SchemaVersion   string                     `json:"schema_version"`
	AccountID       string                     `json:"account_id"`
	Credential      IdentityCredentialDTO      `json:"credential"`
	CredentialAdded bool                       `json:"credential_added"`
	SecurityPosture IdentitySecurityPostureDTO `json:"security_posture"`
	LinkedAt        time.Time                  `json:"linked_at"`
}

// IdentityCredentialLinkCoordinator owns the future production atomic
// boundary for A3 existing-account credential linking.
//
// A production implementation must lock and consume the lifecycle proof
// receipt, mutation ticket, and step-up receipt and bind the credential in one
// PostgreSQL transaction. Any failure must roll back every receipt consumption
// and the identity mutation. The proposed A3 HTTP routes must remain
// non-routable until that implementation and its replay/rollback tests exist.
type IdentityCredentialLinkCoordinator interface {
	CompleteIdentityCredentialLink(
		context.Context,
		IdentityCredentialLinkCommand,
		time.Time,
	) (IdentityCredentialLinkResultDTO, error)
}

type IdentityCredentialLinkService struct {
	coordinator IdentityCredentialLinkCoordinator
	now         func() time.Time
}

func NewIdentityCredentialLinkService(
	coordinator IdentityCredentialLinkCoordinator,
	now func() time.Time,
) (*IdentityCredentialLinkService, error) {
	if coordinator == nil {
		return nil, IdentityDomainError{
			Code:    "identity_credential_link_coordinator_required",
			Message: "identity credential linking requires an atomic transaction coordinator",
		}
	}
	if now == nil {
		now = time.Now
	}
	return &IdentityCredentialLinkService{coordinator: coordinator, now: now}, nil
}

func (service *IdentityCredentialLinkService) Complete(
	ctx context.Context,
	command IdentityCredentialLinkCommand,
) (IdentityCredentialLinkResultDTO, error) {
	command.AccountID = strings.TrimSpace(command.AccountID)
	command.ActorID = strings.TrimSpace(command.ActorID)
	command.SessionID = strings.TrimSpace(command.SessionID)
	command.SessionDigest = strings.TrimSpace(command.SessionDigest)
	command.Provider = normalizeIdentityLifecycleProvider(command.Provider)
	command.TenantID = strings.TrimSpace(command.TenantID)
	command.ProjectID = strings.TrimSpace(command.ProjectID)
	command.ProofReceiptID = strings.TrimSpace(command.ProofReceiptID)
	command.MutationTicketID = strings.TrimSpace(command.MutationTicketID)
	command.StepUpReceiptID = strings.TrimSpace(command.StepUpReceiptID)
	command.IdempotencyKey = strings.TrimSpace(command.IdempotencyKey)

	if command.AccountID == "" || command.ActorID == "" ||
		command.AccountID != command.ActorID {
		return IdentityCredentialLinkResultDTO{}, identityCredentialLinkError(
			"identity_credential_link_actor_mismatch",
			"credential linking requires the matching authenticated account",
		)
	}
	if command.SessionID == "" || !validIdentitySecurityDigest(command.SessionDigest) {
		return IdentityCredentialLinkResultDTO{}, identityCredentialLinkError(
			"identity_credential_link_session_required",
			"credential linking requires a trusted authenticated session",
		)
	}
	if command.TenantID == "" || command.ProjectID == "" {
		return IdentityCredentialLinkResultDTO{}, identityCredentialLinkError(
			"identity_credential_link_scope_required",
			"credential linking requires an explicit tenant and project scope",
		)
	}
	if !validIdentityCredentialLinkProvider(command.Provider) {
		return IdentityCredentialLinkResultDTO{}, identityCredentialLinkError(
			"identity_credential_link_provider_invalid",
			"credential linking provider is invalid",
		)
	}
	if !validIdentityCredentialLinkProofReceipt(command.ProofReceiptID) {
		return IdentityCredentialLinkResultDTO{}, identityCredentialLinkError(
			"identity_credential_link_proof_required",
			"credential linking requires a server-issued proof receipt",
		)
	}
	if !validIdentitySecurityDigest(command.MutationTicketID) ||
		!validIdentitySecurityDigest(command.StepUpReceiptID) {
		return IdentityCredentialLinkResultDTO{}, identityCredentialLinkError(
			"identity_credential_link_authorization_required",
			"credential linking requires mutation-ticket and step-up authorization",
		)
	}
	if !validIdentitySecurityIdempotencyKey(command.IdempotencyKey) {
		return IdentityCredentialLinkResultDTO{}, identityCredentialLinkError(
			"identity_credential_link_idempotency_required",
			"credential linking requires a valid idempotency key",
		)
	}

	result, err := service.coordinator.CompleteIdentityCredentialLink(
		ctx,
		command,
		service.now().UTC(),
	)
	if err != nil {
		return IdentityCredentialLinkResultDTO{}, err
	}
	result.SchemaVersion = IdentityCredentialLinkSchemaVersion
	result.AccountID = strings.TrimSpace(result.AccountID)
	result.Credential.CredentialID = strings.TrimSpace(result.Credential.CredentialID)
	result.Credential.Provider = normalizeIdentityLifecycleProvider(result.Credential.Provider)
	if result.AccountID != command.AccountID ||
		result.Credential.CredentialID == "" ||
		result.Credential.Provider != command.Provider ||
		!result.Credential.Verified ||
		result.LinkedAt.IsZero() {
		return IdentityCredentialLinkResultDTO{}, identityCredentialLinkError(
			"identity_credential_link_result_invalid",
			"credential linking returned an invalid public result",
		)
	}
	result.LinkedAt = result.LinkedAt.UTC()
	return result, nil
}

func validIdentityCredentialLinkProvider(provider IdentityProvider) bool {
	switch provider {
	case IdentityProviderLocal,
		IdentityProviderGitHub,
		IdentityProviderGoogle,
		IdentityProviderWeChat,
		IdentityProviderQQ,
		IdentityProviderAlipay:
		return true
	default:
		return false
	}
}

func validIdentityCredentialLinkProofReceipt(value string) bool {
	if len(value) < 12 || len(value) > 128 || !strings.HasPrefix(value, "ipr_") {
		return false
	}
	for _, character := range value[len("ipr_"):] {
		if (character >= 'a' && character <= 'z') ||
			(character >= 'A' && character <= 'Z') ||
			(character >= '0' && character <= '9') ||
			character == '-' || character == '_' {
			continue
		}
		return false
	}
	return true
}

func identityCredentialLinkError(code, message string) IdentityDomainError {
	return IdentityDomainError{Code: code, Message: message}
}
