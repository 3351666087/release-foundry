package ashrclone

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"strings"
	"sync"
	"time"
)

const (
	IdentityLifecycleSchemaVersion   = "ashr.identity_lifecycle.v1"
	A3IdentitySchemaVersion          = "ashr.clone.a3_identity.v1"
	A3IdentityProvidersSchemaVersion = "ashr.clone.a3_identity.providers.v1"
)

type IdentityLifecycleOperation string

const (
	IdentityOperationRegistration IdentityLifecycleOperation = "registration"
	IdentityOperationLogin        IdentityLifecycleOperation = "login"
)

var (
	ErrIdentityProofReceiptNotFound = errors.New("identity proof receipt not found")
	ErrIdentityProofReceiptConsumed = errors.New("identity proof receipt already consumed")
	ErrIdentityProofReceiptExpired  = errors.New("identity proof receipt expired")
	ErrIdentityProofScopeMismatch   = errors.New("identity proof receipt scope mismatch")
)

// TrustedIdentityProof is produced only by a server-owned verifier. Public
// registration/login completion requests carry an opaque ReceiptID, never a
// caller-controlled verified flag or credential identifier.
type TrustedIdentityProof struct {
	Operation     IdentityLifecycleOperation
	Kind          IdentityCredentialKind
	Provider      IdentityProvider
	Identifier    string
	VerifiedEmail string
	TenantID      string
	ProjectID     string
	DisplayName   string
}

type TrustedIdentityProofRequest struct {
	Operation IdentityLifecycleOperation
	Provider  IdentityProvider
	TenantID  string
	ProjectID string
	Inputs    map[string]string
}

type TrustedIdentityProofResolver interface {
	ResolveTrustedIdentityProof(context.Context, TrustedIdentityProofRequest) (TrustedIdentityProof, error)
}

type IdentityProofReceiptDTO struct {
	SchemaVersion string                     `json:"schema_version"`
	ReceiptID     string                     `json:"receipt_id"`
	Operation     IdentityLifecycleOperation `json:"operation"`
	Provider      IdentityProvider           `json:"provider"`
	TenantID      string                     `json:"tenant_id,omitempty"`
	ProjectID     string                     `json:"project_id,omitempty"`
	ExpiresAt     time.Time                  `json:"expires_at"`
}

type identityProofReceipt struct {
	dto      IdentityProofReceiptDTO
	proof    TrustedIdentityProof
	consumed bool
}

type IdentityLifecycleReceiptStore interface {
	Issue(context.Context, IdentityProofReceiptDTO, TrustedIdentityProof) error
	Consume(context.Context, CompleteIdentityLifecycleRequest, IdentityLifecycleOperation, time.Time) (TrustedIdentityProof, error)
	ProductionDurable() bool
}

type IdentityLifecycleTransactionCoordinator interface {
	CompleteRegistration(context.Context, CompleteIdentityLifecycleRequest, time.Time) (IdentityAccountDTO, error)
	CompleteLogin(context.Context, CompleteIdentityLifecycleRequest, time.Time) (IdentityAuthenticationDTO, error)
}

type IdentityLifecycleOptions struct {
	Now           func() time.Time
	Random        io.Reader
	ReceiptTTL    time.Duration
	ProofResolver TrustedIdentityProofResolver
	ReceiptStore  IdentityLifecycleReceiptStore
	Coordinator   IdentityLifecycleTransactionCoordinator
	GitHubEnabled bool
	GoogleEnabled bool
	Environment   string
}

type IdentityLifecycleService struct {
	identity *UnifiedIdentityService
	store    IdentityLifecycleReceiptStore
	coord    IdentityLifecycleTransactionCoordinator
	now      func() time.Time
	random   io.Reader
	ttl      time.Duration
	resolver TrustedIdentityProofResolver
	github   bool
	google   bool
	env      string
}

func NewIdentityLifecycleService(identity *UnifiedIdentityService, options IdentityLifecycleOptions) (*IdentityLifecycleService, error) {
	if identity == nil && options.Coordinator == nil {
		return nil, fmt.Errorf("unified identity service or transaction coordinator is required")
	}
	if options.Now == nil {
		options.Now = time.Now
	}
	if options.Random == nil {
		options.Random = rand.Reader
	}
	if options.ReceiptTTL <= 0 {
		options.ReceiptTTL = 5 * time.Minute
	}
	environment := strings.TrimSpace(options.Environment)
	if environment == "" {
		environment = "local"
	}
	store := options.ReceiptStore
	if store == nil {
		store = newMemoryIdentityLifecycleReceiptStore()
	}
	if store.ProductionDurable() && options.Coordinator == nil {
		return nil, fmt.Errorf("production identity lifecycle requires an atomic transaction coordinator")
	}
	return &IdentityLifecycleService{
		identity: identity, store: store, coord: options.Coordinator,
		now: options.Now, random: options.Random, ttl: options.ReceiptTTL,
		resolver: options.ProofResolver, github: options.GitHubEnabled,
		google: options.GoogleEnabled, env: environment,
	}, nil
}

func (service *IdentityLifecycleService) Start(ctx context.Context, request TrustedIdentityProofRequest) (IdentityProofReceiptDTO, error) {
	if service.resolver == nil {
		return IdentityProofReceiptDTO{}, IdentityDomainError{
			Code: "trusted_proof_provider_unavailable", Message: "trusted identity proof provider is unavailable",
		}
	}
	request.Operation = IdentityLifecycleOperation(strings.ToLower(strings.TrimSpace(string(request.Operation))))
	request.Provider = normalizeIdentityLifecycleProvider(request.Provider)
	request.TenantID = strings.TrimSpace(request.TenantID)
	request.ProjectID = strings.TrimSpace(request.ProjectID)
	proof, err := service.resolver.ResolveTrustedIdentityProof(ctx, request)
	if err != nil {
		return IdentityProofReceiptDTO{}, err
	}
	if IdentityLifecycleOperation(strings.ToLower(strings.TrimSpace(string(proof.Operation)))) != request.Operation ||
		normalizeIdentityLifecycleProvider(proof.Provider) != request.Provider ||
		strings.TrimSpace(proof.TenantID) != request.TenantID ||
		strings.TrimSpace(proof.ProjectID) != request.ProjectID {
		return IdentityProofReceiptDTO{}, IdentityDomainError{
			Code: "trusted_proof_scope_mismatch", Message: "trusted identity proof does not match the requested scope",
		}
	}
	return service.issueTrustedProofReceiptContext(ctx, proof)
}

// issueTrustedProofReceipt is intentionally package-private so application
// callers cannot bypass Start and mint verified proof receipts directly.
func (service *IdentityLifecycleService) issueTrustedProofReceipt(proof TrustedIdentityProof) (IdentityProofReceiptDTO, error) {
	return service.issueTrustedProofReceiptContext(context.Background(), proof)
}

func (service *IdentityLifecycleService) issueTrustedProofReceiptContext(ctx context.Context, proof TrustedIdentityProof) (IdentityProofReceiptDTO, error) {
	proof.Operation = IdentityLifecycleOperation(strings.ToLower(strings.TrimSpace(string(proof.Operation))))
	proof.Provider = IdentityProvider(strings.ToLower(strings.TrimSpace(string(proof.Provider))))
	proof.TenantID = strings.TrimSpace(proof.TenantID)
	proof.ProjectID = strings.TrimSpace(proof.ProjectID)
	if proof.Operation != IdentityOperationRegistration && proof.Operation != IdentityOperationLogin {
		return IdentityProofReceiptDTO{}, IdentityDomainError{Code: "invalid_identity_operation", Message: "identity operation is invalid"}
	}
	kind, provider, identifier, err := normalizeIdentityCredential(IdentityCredentialInput{
		Kind: proof.Kind, Provider: proof.Provider, Identifier: proof.Identifier, Verified: true,
	})
	if err != nil {
		return IdentityProofReceiptDTO{}, err
	}
	if providerUnavailableForLifecycle(provider, kind) {
		return IdentityProofReceiptDTO{}, IdentityDomainError{Code: "identity_provider_unavailable", Message: "identity provider is unavailable"}
	}
	proof.Kind, proof.Provider, proof.Identifier = kind, provider, identifier
	now := service.now().UTC()
	raw := make([]byte, 32)
	if _, err := io.ReadFull(service.random, raw); err != nil {
		return IdentityProofReceiptDTO{}, fmt.Errorf("generate identity proof receipt: %w", err)
	}
	dto := IdentityProofReceiptDTO{
		SchemaVersion: IdentityLifecycleSchemaVersion,
		ReceiptID:     "ipr_" + base64.RawURLEncoding.EncodeToString(raw),
		Operation:     proof.Operation, Provider: provider,
		TenantID: proof.TenantID, ProjectID: proof.ProjectID, ExpiresAt: now.Add(service.ttl),
	}
	if err := service.store.Issue(ctx, dto, proof); err != nil {
		return IdentityProofReceiptDTO{}, err
	}
	return dto, nil
}

type CompleteIdentityLifecycleRequest struct {
	ReceiptID string
	Provider  IdentityProvider
	TenantID  string
	ProjectID string
}

func (service *IdentityLifecycleService) CompleteRegistration(request CompleteIdentityLifecycleRequest) (IdentityAccountDTO, error) {
	if service.coord != nil {
		return service.coord.CompleteRegistration(context.Background(), request, service.now().UTC())
	}
	proof, err := service.consume(context.Background(), request, IdentityOperationRegistration)
	if err != nil {
		return IdentityAccountDTO{}, err
	}
	credential := IdentityCredentialInput{
		Kind: proof.Kind, Provider: proof.Provider, Identifier: proof.Identifier,
		Verified: true, VerifiedEmail: proof.VerifiedEmail,
	}
	account, err := service.identity.CreateAccount(CreateIdentityAccountRequest{
		DisplayName: proof.DisplayName, InitialCredential: &credential,
	})
	if err != nil {
		return IdentityAccountDTO{}, err
	}
	if account.CredentialCount != 1 || len(account.Credentials) != 1 || !account.Credentials[0].CanLogin {
		return IdentityAccountDTO{}, IdentityDomainError{Code: "registration_credential_required", Message: "registration requires a login-capable credential"}
	}
	return account, nil
}

func (service *IdentityLifecycleService) CompleteLogin(request CompleteIdentityLifecycleRequest) (IdentityAuthenticationDTO, error) {
	if service.coord != nil {
		return service.coord.CompleteLogin(context.Background(), request, service.now().UTC())
	}
	proof, err := service.consume(context.Background(), request, IdentityOperationLogin)
	if err != nil {
		return IdentityAuthenticationDTO{}, err
	}
	// Authentication is deliberately the only identity mutation reachable
	// here. This path never calls CreateAccount, EnsureAccount, LinkCredential,
	// or merge APIs.
	return service.identity.Authenticate(IdentityCredentialInput{
		Kind: proof.Kind, Provider: proof.Provider, Identifier: proof.Identifier, Verified: true,
	})
}

func (service *IdentityLifecycleService) consume(ctx context.Context, request CompleteIdentityLifecycleRequest, operation IdentityLifecycleOperation) (TrustedIdentityProof, error) {
	return service.store.Consume(ctx, request, operation, service.now().UTC())
}

type memoryIdentityLifecycleReceiptStore struct {
	mu       sync.Mutex
	receipts map[string]*identityProofReceipt
}

func (service *IdentityLifecycleService) developmentReceiptCount() int {
	store, ok := service.store.(*memoryIdentityLifecycleReceiptStore)
	if !ok {
		return 0
	}
	store.mu.Lock()
	defer store.mu.Unlock()
	return len(store.receipts)
}

func newMemoryIdentityLifecycleReceiptStore() *memoryIdentityLifecycleReceiptStore {
	return &memoryIdentityLifecycleReceiptStore{receipts: map[string]*identityProofReceipt{}}
}

func (*memoryIdentityLifecycleReceiptStore) ProductionDurable() bool { return false }

func (store *memoryIdentityLifecycleReceiptStore) Issue(_ context.Context, dto IdentityProofReceiptDTO, proof TrustedIdentityProof) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if _, exists := store.receipts[dto.ReceiptID]; exists {
		return fmt.Errorf("identity proof receipt collision")
	}
	store.receipts[dto.ReceiptID] = &identityProofReceipt{dto: dto, proof: proof}
	return nil
}

func (store *memoryIdentityLifecycleReceiptStore) Consume(
	_ context.Context,
	request CompleteIdentityLifecycleRequest,
	operation IdentityLifecycleOperation,
	now time.Time,
) (TrustedIdentityProof, error) {
	receiptID := strings.TrimSpace(request.ReceiptID)
	store.mu.Lock()
	defer store.mu.Unlock()
	receipt, ok := store.receipts[receiptID]
	if !ok {
		return TrustedIdentityProof{}, ErrIdentityProofReceiptNotFound
	}
	if receipt.consumed {
		return TrustedIdentityProof{}, ErrIdentityProofReceiptConsumed
	}
	if !now.Before(receipt.dto.ExpiresAt) {
		receipt.consumed = true
		return TrustedIdentityProof{}, ErrIdentityProofReceiptExpired
	}
	if receipt.proof.Operation != operation ||
		normalizeIdentityLifecycleProvider(request.Provider) != receipt.proof.Provider ||
		strings.TrimSpace(request.TenantID) != receipt.proof.TenantID ||
		strings.TrimSpace(request.ProjectID) != receipt.proof.ProjectID {
		return TrustedIdentityProof{}, ErrIdentityProofScopeMismatch
	}
	receipt.consumed = true
	return receipt.proof, nil
}

type IdentityProviderCapabilityDTO struct {
	Provider                      IdentityProvider `json:"provider"`
	Preferred                     bool             `json:"preferred"`
	Available                     bool             `json:"available"`
	Enabled                       bool             `json:"enabled"`
	CodeCapability                string           `json:"code_capability"`
	DeploymentReadiness           string           `json:"deployment_readiness"`
	DeploymentStatusSource        string           `json:"deployment_status_source"`
	Environment                   string           `json:"environment"`
	QualificationStatus           string           `json:"qualification_status"`
	RequiresBusinessQualification bool             `json:"requires_business_qualification"`
	ReasonCode                    string           `json:"reason_code,omitempty"`
	RegistrationStatus            string           `json:"registration_status"`
	LoginStatus                   string           `json:"login_status"`
	LinkingStatus                 string           `json:"linking_status"`
}

func (service *IdentityLifecycleService) ProviderCapabilities() []IdentityProviderCapabilityDTO {
	return []IdentityProviderCapabilityDTO{
		service.capability(IdentityProviderLocal, true, true, false, "", "proposed"),
		service.capability(IdentityProviderGitHub, false, service.github, false, configurationReason(service.github), "proposed"),
		service.capability(IdentityProviderGoogle, false, service.google, false, configurationReason(service.google), "proposed"),
		service.capability(IdentityProviderWeChat, false, false, true, "business_qualification_required", "unavailable"),
		service.capability(IdentityProviderQQ, false, false, true, "business_qualification_required", "unavailable"),
		service.capability(IdentityProviderAlipay, false, false, true, "business_qualification_required", "unavailable"),
		{
			Provider: "phone", Environment: service.env, QualificationStatus: "unavailable",
			CodeCapability: "contract_only", DeploymentReadiness: "blocked",
			DeploymentStatusSource: "runtime_configuration",
			ReasonCode:             "phone_verification_unavailable", RegistrationStatus: "unavailable",
			LoginStatus: "unavailable", LinkingStatus: "unavailable",
		},
	}
}

func (service *IdentityLifecycleService) capability(provider IdentityProvider, preferred, enabled, qualification bool, reason, linkingStatus string) IdentityProviderCapabilityDTO {
	status := "unavailable"
	if enabled {
		status = "available"
	}
	qualificationStatus := "not_required"
	if qualification {
		qualificationStatus = "required"
	}
	codeCapability := "implemented"
	deploymentReadiness := "ready"
	deploymentStatusSource := "runtime_configuration"
	if qualification {
		codeCapability = "adapter_only"
		deploymentReadiness = "blocked"
		deploymentStatusSource = "business_qualification"
	} else if !enabled {
		deploymentReadiness = "configuration_required"
	}
	return IdentityProviderCapabilityDTO{
		Provider: provider, Preferred: preferred, Available: enabled, Enabled: enabled,
		CodeCapability: codeCapability, DeploymentReadiness: deploymentReadiness,
		DeploymentStatusSource: deploymentStatusSource,
		Environment:            service.env, QualificationStatus: qualificationStatus,
		RequiresBusinessQualification: qualification, ReasonCode: reason,
		RegistrationStatus: status, LoginStatus: status, LinkingStatus: linkingStatus,
	}
}

func normalizeIdentityLifecycleProvider(provider IdentityProvider) IdentityProvider {
	normalized := IdentityProvider(strings.ToLower(strings.TrimSpace(string(provider))))
	if normalized == IdentityProvider("email") {
		return IdentityProviderLocal
	}
	return normalized
}

func providerUnavailableForLifecycle(provider IdentityProvider, kind IdentityCredentialKind) bool {
	return kind == IdentityCredentialPhone ||
		provider == IdentityProviderWeChat || provider == IdentityProviderQQ || provider == IdentityProviderAlipay
}

func configurationReason(enabled bool) string {
	if enabled {
		return ""
	}
	return "provider_not_configured"
}

func (service *UnifiedIdentityService) IdentityObjectCounts() (accounts, credentials int) {
	service.mu.RLock()
	defer service.mu.RUnlock()
	return len(service.accounts), len(service.credentials)
}
