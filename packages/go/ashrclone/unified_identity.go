package ashrclone

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"sort"
	"strings"
	"sync"
	"time"
)

const UnifiedIdentitySchemaVersion = "ashr.unified_identity.v1"

type IdentityCredentialKind string

const (
	IdentityCredentialOAuth IdentityCredentialKind = "oauth"
	IdentityCredentialPhone IdentityCredentialKind = "phone"
	IdentityCredentialEmail IdentityCredentialKind = "email"
)

type IdentityProvider string

const (
	IdentityProviderGitHub IdentityProvider = "github"
	IdentityProviderGoogle IdentityProvider = "google"
	IdentityProviderWeChat IdentityProvider = "wechat"
	IdentityProviderQQ     IdentityProvider = "qq"
	IdentityProviderAlipay IdentityProvider = "alipay"
	IdentityProviderLocal  IdentityProvider = "local"
)

var (
	ErrIdentityAccountNotFound    = errors.New("identity account not found")
	ErrIdentityCredentialNotFound = errors.New("identity credential not found")
	ErrIdentityMergePlanNotFound  = errors.New("identity merge plan not found")
)

type IdentityDomainError struct {
	Code    string
	Message string
}

func (err IdentityDomainError) Error() string {
	if strings.TrimSpace(err.Message) != "" {
		return err.Message
	}
	return err.Code
}

type IdentityCredentialInput struct {
	Kind       IdentityCredentialKind
	Provider   IdentityProvider
	Identifier string
	Verified   bool
}

type CreateIdentityAccountRequest struct {
	DisplayName       string
	InitialCredential *IdentityCredentialInput
}

type LinkIdentityCredentialRequest struct {
	Credential IdentityCredentialInput
	ActorID    string
}

type IdentityMembershipRequest struct {
	TenantID  string
	ProjectID string
	Role      string
	ActorID   string
}

type IdentityMergeRequest struct {
	SourceAccountID string
	TargetAccountID string
	ActorID         string
	Reason          string
}

type IdentityAccountDTO struct {
	SchemaVersion   string                  `json:"schema_version"`
	AccountID       string                  `json:"account_id"`
	PrimaryID       string                  `json:"primary_principal_id"`
	DisplayName     string                  `json:"display_name,omitempty"`
	Status          string                  `json:"status"`
	Credentials     []IdentityCredentialDTO `json:"credentials"`
	Memberships     []IdentityMembershipDTO `json:"memberships"`
	CredentialCount int                     `json:"credential_count"`
	MembershipCount int                     `json:"membership_count"`
	CreatedAt       time.Time               `json:"created_at"`
	UpdatedAt       time.Time               `json:"updated_at"`
}

type IdentityCredentialDTO struct {
	SchemaVersion string                 `json:"schema_version"`
	CredentialID  string                 `json:"credential_id"`
	Kind          IdentityCredentialKind `json:"kind"`
	Provider      IdentityProvider       `json:"provider"`
	Verified      bool                   `json:"verified"`
	CanLogin      bool                   `json:"can_login"`
	LinkedAt      time.Time              `json:"linked_at"`
	LastUsedAt    *time.Time             `json:"last_used_at,omitempty"`
}

type IdentityMembershipDTO struct {
	SchemaVersion string    `json:"schema_version"`
	MembershipID  string    `json:"membership_id"`
	AccountID     string    `json:"account_id"`
	TenantID      string    `json:"tenant_id"`
	ProjectID     string    `json:"project_id,omitempty"`
	Role          string    `json:"role"`
	CreatedAt     time.Time `json:"created_at"`
	UpdatedAt     time.Time `json:"updated_at"`
}

type IdentityAuthenticationDTO struct {
	SchemaVersion string                  `json:"schema_version"`
	Account       IdentityAccountDTO      `json:"account"`
	PrincipalID   string                  `json:"principal_id"`
	Credential    IdentityCredentialDTO   `json:"credential"`
	Memberships   []IdentityMembershipDTO `json:"memberships"`
	Authenticated time.Time               `json:"authenticated_at"`
}

type IdentityMergeConflictDTO struct {
	Code       string `json:"code"`
	TenantID   string `json:"tenant_id,omitempty"`
	ProjectID  string `json:"project_id,omitempty"`
	Resolution string `json:"resolution"`
}

type IdentityMergePlanDTO struct {
	SchemaVersion         string                     `json:"schema_version"`
	PlanID                string                     `json:"plan_id"`
	SourceAccountID       string                     `json:"source_account_id"`
	TargetAccountID       string                     `json:"target_account_id"`
	CredentialsToMove     []string                   `json:"credential_ids_to_move"`
	MembershipsToMove     []string                   `json:"membership_ids_to_move"`
	MembershipConflicts   []IdentityMergeConflictDTO `json:"membership_conflicts"`
	SourceCredentialCount int                        `json:"source_credential_count"`
	TargetCredentialCount int                        `json:"target_credential_count"`
	ResultCredentialCount int                        `json:"result_credential_count"`
	SourceMembershipCount int                        `json:"source_membership_count"`
	TargetMembershipCount int                        `json:"target_membership_count"`
	ResultMembershipCount int                        `json:"result_membership_count"`
	ReasonPresent         bool                       `json:"reason_present"`
	CreatedAt             time.Time                  `json:"created_at"`
	ExpiresAt             time.Time                  `json:"expires_at"`
	Executed              bool                       `json:"executed"`
}

type IdentityMergeResultDTO struct {
	SchemaVersion     string             `json:"schema_version"`
	PlanID            string             `json:"plan_id"`
	SourceAccountID   string             `json:"source_account_id"`
	TargetAccount     IdentityAccountDTO `json:"target_account"`
	MovedCredentials  int                `json:"moved_credentials"`
	MovedMemberships  int                `json:"moved_memberships"`
	ResolvedConflicts int                `json:"resolved_membership_conflicts"`
	ExecutedAt        time.Time          `json:"executed_at"`
}

type IdentityAuditEventDTO struct {
	SchemaVersion string         `json:"schema_version"`
	EventID       string         `json:"event_id"`
	Action        string         `json:"action"`
	ActorPresent  bool           `json:"actor_present"`
	SubjectType   string         `json:"subject_type"`
	SubjectID     string         `json:"subject_id"`
	Outcome       string         `json:"outcome"`
	Details       map[string]any `json:"details,omitempty"`
	PreviousHash  string         `json:"previous_hash,omitempty"`
	EventHash     string         `json:"event_hash"`
	CreatedAt     time.Time      `json:"created_at"`
}

type UnifiedIdentityServiceOptions struct {
	Now            func() time.Time
	Random         io.Reader
	FingerprintKey []byte
	MergePlanTTL   time.Duration
}

type identityAccount struct {
	id            string
	primaryID     string
	displayName   string
	status        string
	credentialIDs map[string]struct{}
	membershipIDs map[string]struct{}
	revision      uint64
	createdAt     time.Time
	updatedAt     time.Time
}

type identityPrincipal struct {
	id        string
	accountID string
	status    string
	createdAt time.Time
}

type identityCredential struct {
	id           string
	accountID    string
	principalID  string
	kind         IdentityCredentialKind
	provider     IdentityProvider
	lookupDigest string
	verified     bool
	canLogin     bool
	linkedAt     time.Time
	lastUsedAt   *time.Time
}

type identityMembership struct {
	id        string
	accountID string
	tenantID  string
	projectID string
	role      string
	createdAt time.Time
	updatedAt time.Time
}

type identityMergePlan struct {
	dto            IdentityMergePlanDTO
	sourceRevision uint64
	targetRevision uint64
	actorID        string
	reasonDigest   string
}

type UnifiedIdentityService struct {
	mu sync.RWMutex

	accounts         map[string]*identityAccount
	principals       map[string]*identityPrincipal
	credentials      map[string]*identityCredential
	credentialOwners map[string]string
	memberships      map[string]*identityMembership
	mergePlans       map[string]*identityMergePlan
	auditEvents      []IdentityAuditEventDTO

	now            func() time.Time
	random         io.Reader
	fingerprintKey []byte
	mergePlanTTL   time.Duration
}

func NewUnifiedIdentityService(options UnifiedIdentityServiceOptions) (*UnifiedIdentityService, error) {
	if options.Now == nil {
		options.Now = time.Now
	}
	if options.Random == nil {
		options.Random = rand.Reader
	}
	if options.MergePlanTTL <= 0 {
		options.MergePlanTTL = 10 * time.Minute
	}
	key := append([]byte(nil), options.FingerprintKey...)
	if len(key) == 0 {
		key = make([]byte, sha256.Size)
		if _, err := io.ReadFull(options.Random, key); err != nil {
			return nil, fmt.Errorf("initialize identity fingerprint key: %w", err)
		}
	}
	if len(key) < 16 {
		return nil, fmt.Errorf("identity fingerprint key must be at least 16 bytes")
	}
	return &UnifiedIdentityService{
		accounts: make(map[string]*identityAccount), principals: make(map[string]*identityPrincipal),
		credentials: make(map[string]*identityCredential), credentialOwners: make(map[string]string),
		memberships: make(map[string]*identityMembership), mergePlans: make(map[string]*identityMergePlan),
		auditEvents: []IdentityAuditEventDTO{}, now: options.Now, random: options.Random,
		fingerprintKey: key, mergePlanTTL: options.MergePlanTTL,
	}, nil
}

func (service *UnifiedIdentityService) CreateAccount(request CreateIdentityAccountRequest) (IdentityAccountDTO, error) {
	service.mu.Lock()
	defer service.mu.Unlock()

	now := service.now().UTC()
	accountID, err := service.newID("acct")
	if err != nil {
		return IdentityAccountDTO{}, err
	}
	principalID, err := service.newID("prn")
	if err != nil {
		return IdentityAccountDTO{}, err
	}
	account := &identityAccount{
		id: accountID, primaryID: principalID, displayName: strings.TrimSpace(request.DisplayName), status: "active",
		credentialIDs: make(map[string]struct{}), membershipIDs: make(map[string]struct{}),
		revision: 1, createdAt: now, updatedAt: now,
	}
	service.accounts[accountID] = account
	service.principals[principalID] = &identityPrincipal{id: principalID, accountID: accountID, status: "active", createdAt: now}
	if request.InitialCredential != nil {
		if _, err := service.linkCredentialLocked(account, *request.InitialCredential, accountID, now); err != nil {
			delete(service.principals, principalID)
			delete(service.accounts, accountID)
			return IdentityAccountDTO{}, err
		}
	}
	service.appendAuditLocked("identity.account.created", accountID, "account", accountID, "success", map[string]any{
		"initial_credential_present": request.InitialCredential != nil,
		"display_name_present":       account.displayName != "",
	}, now)
	return service.accountDTOLocked(account), nil
}

func (service *UnifiedIdentityService) EnsureAccount(accountID, actorID string) (IdentityAccountDTO, error) {
	service.mu.Lock()
	defer service.mu.Unlock()

	accountID = strings.TrimSpace(accountID)
	if accountID == "" || len(accountID) > 256 || strings.ContainsAny(accountID, " \t\r\n/") {
		return IdentityAccountDTO{}, IdentityDomainError{Code: "invalid_account_id", Message: "canonical account_id is invalid"}
	}
	if existing, ok := service.accounts[accountID]; ok {
		if existing.status != "active" {
			return IdentityAccountDTO{}, IdentityDomainError{Code: "identity_account_inactive", Message: "identity account is not active"}
		}
		return service.accountDTOLocked(existing), nil
	}
	principalID, err := service.newID("prn")
	if err != nil {
		return IdentityAccountDTO{}, err
	}
	now := service.now().UTC()
	account := &identityAccount{
		id: accountID, primaryID: principalID, status: "active",
		credentialIDs: make(map[string]struct{}), membershipIDs: make(map[string]struct{}),
		revision: 1, createdAt: now, updatedAt: now,
	}
	service.accounts[accountID] = account
	service.principals[principalID] = &identityPrincipal{id: principalID, accountID: accountID, status: "active", createdAt: now}
	service.appendAuditLocked("identity.account.ensured", actorID, "account", accountID, "success", map[string]any{
		"trusted_external_account_id": true,
	}, now)
	return service.accountDTOLocked(account), nil
}

func (service *UnifiedIdentityService) GetAccount(accountID string) (IdentityAccountDTO, error) {
	service.mu.RLock()
	defer service.mu.RUnlock()
	account, err := service.activeAccountLocked(accountID)
	if err != nil {
		return IdentityAccountDTO{}, err
	}
	return service.accountDTOLocked(account), nil
}

func (service *UnifiedIdentityService) LinkCredential(accountID string, request LinkIdentityCredentialRequest) (IdentityCredentialDTO, error) {
	credential, _, err := service.LinkCredentialWithStatus(accountID, request)
	return credential, err
}

func (service *UnifiedIdentityService) LinkCredentialWithStatus(accountID string, request LinkIdentityCredentialRequest) (IdentityCredentialDTO, bool, error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	account, err := service.activeAccountLocked(accountID)
	if err != nil {
		return IdentityCredentialDTO{}, false, err
	}
	now := service.now().UTC()
	credential, created, err := service.linkCredentialLockedWithStatus(account, request.Credential, request.ActorID, now)
	if err != nil {
		service.appendAuditLocked("identity.credential.link", request.ActorID, "account", accountID, "rejected", map[string]any{
			"kind": request.Credential.Kind, "provider": request.Credential.Provider, "reason": identityErrorCode(err),
		}, now)
		return IdentityCredentialDTO{}, false, err
	}
	service.appendAuditLocked("identity.credential.link", request.ActorID, "credential", credential.id, "success", map[string]any{
		"account_id": accountID, "kind": credential.kind, "provider": credential.provider,
		"verified": credential.verified, "created": created,
	}, now)
	return identityCredentialDTO(credential), created, nil
}

func (service *UnifiedIdentityService) Authenticate(input IdentityCredentialInput) (IdentityAuthenticationDTO, error) {
	kind, provider, normalized, err := normalizeIdentityCredential(input)
	if err != nil {
		return IdentityAuthenticationDTO{}, err
	}
	if !input.Verified {
		return IdentityAuthenticationDTO{}, IdentityDomainError{Code: "credential_verification_required", Message: "authentication requires a verified credential assertion"}
	}

	service.mu.Lock()
	defer service.mu.Unlock()
	digest := service.credentialDigest(kind, provider, normalized)
	credentialID, ok := service.credentialOwners[digest]
	if !ok {
		return IdentityAuthenticationDTO{}, ErrIdentityCredentialNotFound
	}
	credential := service.credentials[credentialID]
	account, ok := service.accounts[credential.accountID]
	if !ok || account.status != "active" || !credential.verified || !credential.canLogin {
		return IdentityAuthenticationDTO{}, IdentityDomainError{Code: "credential_not_login_capable", Message: "credential cannot authenticate an active account"}
	}
	now := service.now().UTC()
	credential.lastUsedAt = &now
	service.appendAuditLocked("identity.authentication.succeeded", account.id, "credential", credential.id, "success", map[string]any{
		"account_id": account.id, "kind": credential.kind, "provider": credential.provider,
	}, now)
	accountDTO := service.accountDTOLocked(account)
	return IdentityAuthenticationDTO{
		SchemaVersion: UnifiedIdentitySchemaVersion, Account: accountDTO, PrincipalID: credential.principalID,
		Credential: identityCredentialDTO(credential), Memberships: accountDTO.Memberships, Authenticated: now,
	}, nil
}

func (service *UnifiedIdentityService) UnlinkCredential(accountID, credentialID, actorID string) (IdentityCredentialDTO, error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	account, err := service.activeAccountLocked(accountID)
	if err != nil {
		return IdentityCredentialDTO{}, err
	}
	credential, ok := service.credentials[strings.TrimSpace(credentialID)]
	if !ok || credential.accountID != account.id {
		return IdentityCredentialDTO{}, ErrIdentityCredentialNotFound
	}
	if credential.canLogin && service.loginCredentialCountLocked(account) <= 1 {
		err := IdentityDomainError{Code: "last_login_credential", Message: "the final login-capable credential cannot be unlinked"}
		service.appendAuditLocked("identity.credential.unlink", actorID, "credential", credential.id, "rejected", map[string]any{
			"account_id": account.id, "reason": err.Code,
		}, service.now().UTC())
		return IdentityCredentialDTO{}, err
	}
	now := service.now().UTC()
	dto := identityCredentialDTO(credential)
	delete(account.credentialIDs, credential.id)
	delete(service.credentialOwners, credential.lookupDigest)
	delete(service.credentials, credential.id)
	account.revision++
	account.updatedAt = now
	service.appendAuditLocked("identity.credential.unlink", actorID, "credential", credential.id, "success", map[string]any{
		"account_id": account.id, "kind": credential.kind, "provider": credential.provider,
	}, now)
	return dto, nil
}

func (service *UnifiedIdentityService) CanUnlinkCredential(accountID, credentialID string) error {
	service.mu.RLock()
	defer service.mu.RUnlock()
	account, err := service.activeAccountLocked(accountID)
	if err != nil {
		return err
	}
	credential, ok := service.credentials[strings.TrimSpace(credentialID)]
	if !ok || credential.accountID != account.id {
		return ErrIdentityCredentialNotFound
	}
	if credential.canLogin && service.loginCredentialCountLocked(account) <= 1 {
		return IdentityDomainError{Code: "last_login_credential", Message: "the final login-capable credential cannot be unlinked"}
	}
	return nil
}

func (service *UnifiedIdentityService) AddMembership(accountID string, request IdentityMembershipRequest) (IdentityMembershipDTO, error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	account, err := service.activeAccountLocked(accountID)
	if err != nil {
		return IdentityMembershipDTO{}, err
	}
	tenantID, projectID, role := strings.TrimSpace(request.TenantID), strings.TrimSpace(request.ProjectID), strings.ToLower(strings.TrimSpace(request.Role))
	if tenantID == "" || role == "" {
		return IdentityMembershipDTO{}, IdentityDomainError{Code: "invalid_membership", Message: "tenant_id and role are required"}
	}
	for membershipID := range account.membershipIDs {
		existing := service.memberships[membershipID]
		if existing.tenantID == tenantID && existing.projectID == projectID {
			if existing.role != role {
				return IdentityMembershipDTO{}, IdentityDomainError{Code: "membership_conflict", Message: "account already has a different role in this scope"}
			}
			return identityMembershipDTO(existing), nil
		}
	}
	membershipID, err := service.newID("mbr")
	if err != nil {
		return IdentityMembershipDTO{}, err
	}
	now := service.now().UTC()
	membership := &identityMembership{
		id: membershipID, accountID: account.id, tenantID: tenantID, projectID: projectID,
		role: role, createdAt: now, updatedAt: now,
	}
	service.memberships[membershipID] = membership
	account.membershipIDs[membershipID] = struct{}{}
	account.revision++
	account.updatedAt = now
	service.appendAuditLocked("identity.membership.add", request.ActorID, "membership", membership.id, "success", map[string]any{
		"account_id": account.id, "tenant_id": tenantID, "project_id": projectID, "role": role,
	}, now)
	return identityMembershipDTO(membership), nil
}

func (service *UnifiedIdentityService) PlanMerge(request IdentityMergeRequest) (IdentityMergePlanDTO, error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	source, err := service.activeAccountLocked(request.SourceAccountID)
	if err != nil {
		return IdentityMergePlanDTO{}, err
	}
	target, err := service.activeAccountLocked(request.TargetAccountID)
	if err != nil {
		return IdentityMergePlanDTO{}, err
	}
	if source.id == target.id {
		return IdentityMergePlanDTO{}, IdentityDomainError{Code: "same_account_merge", Message: "source and target accounts must differ"}
	}
	planID, err := service.newID("merge")
	if err != nil {
		return IdentityMergePlanDTO{}, err
	}
	now := service.now().UTC()
	credentialIDs := sortedIdentitySet(source.credentialIDs)
	membershipIDs := make([]string, 0, len(source.membershipIDs))
	conflicts := []IdentityMergeConflictDTO{}
	resultMembershipCount := len(target.membershipIDs)
	for _, sourceMembershipID := range sortedIdentitySet(source.membershipIDs) {
		sourceMembership := service.memberships[sourceMembershipID]
		targetMembership := service.membershipForScopeLocked(target, sourceMembership.tenantID, sourceMembership.projectID)
		if targetMembership == nil {
			membershipIDs = append(membershipIDs, sourceMembershipID)
			resultMembershipCount++
			continue
		}
		resolution := "retain_target_membership"
		if targetMembership.role == sourceMembership.role {
			resolution = "deduplicate_membership"
		}
		conflicts = append(conflicts, IdentityMergeConflictDTO{
			Code: "membership_scope_overlap", TenantID: sourceMembership.tenantID,
			ProjectID: sourceMembership.projectID, Resolution: resolution,
		})
	}
	dto := IdentityMergePlanDTO{
		SchemaVersion: UnifiedIdentitySchemaVersion, PlanID: planID, SourceAccountID: source.id, TargetAccountID: target.id,
		CredentialsToMove: credentialIDs, MembershipsToMove: membershipIDs, MembershipConflicts: conflicts,
		SourceCredentialCount: len(source.credentialIDs), TargetCredentialCount: len(target.credentialIDs),
		ResultCredentialCount: len(source.credentialIDs) + len(target.credentialIDs),
		SourceMembershipCount: len(source.membershipIDs), TargetMembershipCount: len(target.membershipIDs),
		ResultMembershipCount: resultMembershipCount, ReasonPresent: strings.TrimSpace(request.Reason) != "",
		CreatedAt: now, ExpiresAt: now.Add(service.mergePlanTTL),
	}
	service.mergePlans[planID] = &identityMergePlan{
		dto: dto, sourceRevision: source.revision, targetRevision: target.revision, actorID: strings.TrimSpace(request.ActorID),
		reasonDigest: service.privateDigest(strings.TrimSpace(request.Reason)),
	}
	service.appendAuditLocked("identity.merge.plan", request.ActorID, "merge_plan", planID, "success", map[string]any{
		"source_account_id": source.id, "target_account_id": target.id, "credential_count": len(credentialIDs),
		"membership_count": len(membershipIDs), "conflict_count": len(conflicts), "reason_present": dto.ReasonPresent,
	}, now)
	return cloneIdentityMergePlanDTO(dto), nil
}

func (service *UnifiedIdentityService) ExecuteMerge(planID, actorID string) (IdentityMergeResultDTO, error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	plan, ok := service.mergePlans[strings.TrimSpace(planID)]
	if !ok {
		return IdentityMergeResultDTO{}, ErrIdentityMergePlanNotFound
	}
	now := service.now().UTC()
	if plan.dto.Executed {
		return IdentityMergeResultDTO{}, IdentityDomainError{Code: "merge_plan_already_executed", Message: "merge plan has already been executed"}
	}
	if !now.Before(plan.dto.ExpiresAt) {
		return IdentityMergeResultDTO{}, IdentityDomainError{Code: "merge_plan_expired", Message: "merge plan has expired"}
	}
	if plan.actorID != "" && strings.TrimSpace(actorID) != plan.actorID {
		return IdentityMergeResultDTO{}, IdentityDomainError{Code: "merge_actor_mismatch", Message: "merge must be executed by the actor that created the plan"}
	}
	source, sourceOK := service.accounts[plan.dto.SourceAccountID]
	target, targetOK := service.accounts[plan.dto.TargetAccountID]
	if !sourceOK || !targetOK || source.status != "active" || target.status != "active" {
		return IdentityMergeResultDTO{}, IdentityDomainError{Code: "merge_account_inactive", Message: "merge source and target must both be active"}
	}
	if source.revision != plan.sourceRevision || target.revision != plan.targetRevision {
		return IdentityMergeResultDTO{}, IdentityDomainError{Code: "stale_merge_plan", Message: "account state changed after the merge plan was created"}
	}

	movedCredentials := 0
	for credentialID := range source.credentialIDs {
		credential := service.credentials[credentialID]
		credential.accountID = target.id
		credential.principalID = target.primaryID
		target.credentialIDs[credentialID] = struct{}{}
		delete(source.credentialIDs, credentialID)
		movedCredentials++
	}
	movedMemberships, resolvedConflicts := 0, 0
	for membershipID := range source.membershipIDs {
		membership := service.memberships[membershipID]
		if service.membershipForScopeLocked(target, membership.tenantID, membership.projectID) != nil {
			delete(service.memberships, membershipID)
			delete(source.membershipIDs, membershipID)
			resolvedConflicts++
			continue
		}
		membership.accountID = target.id
		membership.updatedAt = now
		target.membershipIDs[membershipID] = struct{}{}
		delete(source.membershipIDs, membershipID)
		movedMemberships++
	}
	for _, principal := range service.principals {
		if principal.accountID == source.id {
			principal.status = "merged"
		}
	}
	source.status = "merged"
	source.updatedAt = now
	source.revision++
	target.updatedAt = now
	target.revision++
	plan.dto.Executed = true
	service.appendAuditLocked("identity.merge.execute", actorID, "merge_plan", plan.dto.PlanID, "success", map[string]any{
		"source_account_id": source.id, "target_account_id": target.id, "moved_credentials": movedCredentials,
		"moved_memberships": movedMemberships, "resolved_membership_conflicts": resolvedConflicts,
	}, now)
	return IdentityMergeResultDTO{
		SchemaVersion: UnifiedIdentitySchemaVersion, PlanID: plan.dto.PlanID, SourceAccountID: source.id,
		TargetAccount: service.accountDTOLocked(target), MovedCredentials: movedCredentials,
		MovedMemberships: movedMemberships, ResolvedConflicts: resolvedConflicts, ExecutedAt: now,
	}, nil
}

func (service *UnifiedIdentityService) AuditEvents() []IdentityAuditEventDTO {
	service.mu.RLock()
	defer service.mu.RUnlock()
	result := make([]IdentityAuditEventDTO, len(service.auditEvents))
	for index, event := range service.auditEvents {
		result[index] = event
		result[index].Details = cloneIdentityDetails(event.Details)
	}
	return result
}

func (service *UnifiedIdentityService) linkCredentialLocked(account *identityAccount, input IdentityCredentialInput, actorID string, now time.Time) (*identityCredential, error) {
	credential, _, err := service.linkCredentialLockedWithStatus(account, input, actorID, now)
	return credential, err
}

func (service *UnifiedIdentityService) linkCredentialLockedWithStatus(account *identityAccount, input IdentityCredentialInput, actorID string, now time.Time) (*identityCredential, bool, error) {
	kind, provider, normalized, err := normalizeIdentityCredential(input)
	if err != nil {
		return nil, false, err
	}
	if !input.Verified {
		return nil, false, IdentityDomainError{Code: "credential_verification_required", Message: "only verified credentials can be linked"}
	}
	digest := service.credentialDigest(kind, provider, normalized)
	if credentialID, ok := service.credentialOwners[digest]; ok {
		existing := service.credentials[credentialID]
		if existing.accountID != account.id {
			return nil, false, IdentityDomainError{Code: "credential_link_conflict", Message: "credential is already linked to another account"}
		}
		return existing, false, nil
	}
	credentialID, err := service.newID("cred")
	if err != nil {
		return nil, false, err
	}
	credential := &identityCredential{
		id: credentialID, accountID: account.id, principalID: account.primaryID, kind: kind, provider: provider,
		lookupDigest: digest, verified: true, canLogin: true, linkedAt: now,
	}
	service.credentials[credentialID] = credential
	service.credentialOwners[digest] = credentialID
	account.credentialIDs[credentialID] = struct{}{}
	account.revision++
	account.updatedAt = now
	_ = actorID
	return credential, true, nil
}

func normalizeIdentityCredential(input IdentityCredentialInput) (IdentityCredentialKind, IdentityProvider, string, error) {
	kind := IdentityCredentialKind(strings.ToLower(strings.TrimSpace(string(input.Kind))))
	provider := IdentityProvider(strings.ToLower(strings.TrimSpace(string(input.Provider))))
	identifier := strings.TrimSpace(input.Identifier)
	if identifier == "" {
		return "", "", "", IdentityDomainError{Code: "invalid_credential", Message: "credential identifier is required"}
	}
	switch kind {
	case IdentityCredentialOAuth:
		switch provider {
		case IdentityProviderGitHub, IdentityProviderGoogle, IdentityProviderWeChat, IdentityProviderQQ, IdentityProviderAlipay:
		default:
			return "", "", "", IdentityDomainError{Code: "unsupported_identity_provider", Message: "unsupported OAuth identity provider"}
		}
	case IdentityCredentialEmail:
		if provider != "" && provider != IdentityProviderLocal {
			return "", "", "", IdentityDomainError{Code: "invalid_credential_provider", Message: "email credentials use the local provider"}
		}
		provider = IdentityProviderLocal
		identifier = strings.ToLower(identifier)
		at := strings.LastIndex(identifier, "@")
		if at <= 0 || at == len(identifier)-1 || strings.ContainsAny(identifier, " \t\r\n") {
			return "", "", "", IdentityDomainError{Code: "invalid_email", Message: "email credential is invalid"}
		}
	case IdentityCredentialPhone:
		if provider != "" && provider != IdentityProviderLocal {
			return "", "", "", IdentityDomainError{Code: "invalid_credential_provider", Message: "phone credentials use the local provider"}
		}
		provider = IdentityProviderLocal
		identifier = strings.NewReplacer(" ", "", "-", "", "(", "", ")", "").Replace(identifier)
		if strings.HasPrefix(identifier, "00") {
			identifier = "+" + strings.TrimPrefix(identifier, "00")
		}
		digits := strings.TrimPrefix(identifier, "+")
		if len(digits) < 7 || len(digits) > 15 || strings.Trim(digits, "0123456789") != "" {
			return "", "", "", IdentityDomainError{Code: "invalid_phone", Message: "phone credential must be a valid international number"}
		}
	default:
		return "", "", "", IdentityDomainError{Code: "unsupported_credential_kind", Message: "credential kind must be oauth, phone, or email"}
	}
	return kind, provider, identifier, nil
}

func (service *UnifiedIdentityService) activeAccountLocked(accountID string) (*identityAccount, error) {
	account, ok := service.accounts[strings.TrimSpace(accountID)]
	if !ok {
		return nil, ErrIdentityAccountNotFound
	}
	if account.status != "active" {
		return nil, IdentityDomainError{Code: "identity_account_inactive", Message: "identity account is not active"}
	}
	return account, nil
}

func (service *UnifiedIdentityService) accountDTOLocked(account *identityAccount) IdentityAccountDTO {
	credentials := make([]IdentityCredentialDTO, 0, len(account.credentialIDs))
	for credentialID := range account.credentialIDs {
		credentials = append(credentials, identityCredentialDTO(service.credentials[credentialID]))
	}
	sort.Slice(credentials, func(i, j int) bool { return credentials[i].CredentialID < credentials[j].CredentialID })
	memberships := make([]IdentityMembershipDTO, 0, len(account.membershipIDs))
	for membershipID := range account.membershipIDs {
		memberships = append(memberships, identityMembershipDTO(service.memberships[membershipID]))
	}
	sort.Slice(memberships, func(i, j int) bool {
		if memberships[i].TenantID != memberships[j].TenantID {
			return memberships[i].TenantID < memberships[j].TenantID
		}
		if memberships[i].ProjectID != memberships[j].ProjectID {
			return memberships[i].ProjectID < memberships[j].ProjectID
		}
		return memberships[i].MembershipID < memberships[j].MembershipID
	})
	return IdentityAccountDTO{
		SchemaVersion: UnifiedIdentitySchemaVersion, AccountID: account.id, PrimaryID: account.primaryID,
		DisplayName: account.displayName, Status: account.status, Credentials: credentials, Memberships: memberships,
		CredentialCount: len(credentials), MembershipCount: len(memberships), CreatedAt: account.createdAt, UpdatedAt: account.updatedAt,
	}
}

func identityCredentialDTO(credential *identityCredential) IdentityCredentialDTO {
	dto := IdentityCredentialDTO{
		SchemaVersion: UnifiedIdentitySchemaVersion, CredentialID: credential.id, Kind: credential.kind,
		Provider: credential.provider, Verified: credential.verified, CanLogin: credential.canLogin, LinkedAt: credential.linkedAt,
	}
	if credential.lastUsedAt != nil {
		value := *credential.lastUsedAt
		dto.LastUsedAt = &value
	}
	return dto
}

func identityMembershipDTO(membership *identityMembership) IdentityMembershipDTO {
	return IdentityMembershipDTO{
		SchemaVersion: UnifiedIdentitySchemaVersion, MembershipID: membership.id, AccountID: membership.accountID,
		TenantID: membership.tenantID, ProjectID: membership.projectID, Role: membership.role,
		CreatedAt: membership.createdAt, UpdatedAt: membership.updatedAt,
	}
}

func (service *UnifiedIdentityService) loginCredentialCountLocked(account *identityAccount) int {
	count := 0
	for credentialID := range account.credentialIDs {
		if credential := service.credentials[credentialID]; credential != nil && credential.verified && credential.canLogin {
			count++
		}
	}
	return count
}

func (service *UnifiedIdentityService) membershipForScopeLocked(account *identityAccount, tenantID, projectID string) *identityMembership {
	for membershipID := range account.membershipIDs {
		membership := service.memberships[membershipID]
		if membership.tenantID == tenantID && membership.projectID == projectID {
			return membership
		}
	}
	return nil
}

func (service *UnifiedIdentityService) credentialDigest(kind IdentityCredentialKind, provider IdentityProvider, normalized string) string {
	return service.privateDigest(string(kind) + "\x00" + string(provider) + "\x00" + normalized)
}

func (service *UnifiedIdentityService) privateDigest(value string) string {
	if value == "" {
		return ""
	}
	mac := hmac.New(sha256.New, service.fingerprintKey)
	_, _ = mac.Write([]byte(value))
	return hex.EncodeToString(mac.Sum(nil))
}

func (service *UnifiedIdentityService) newID(prefix string) (string, error) {
	for attempt := 0; attempt < 8; attempt++ {
		raw := make([]byte, 12)
		if _, err := io.ReadFull(service.random, raw); err != nil {
			return "", fmt.Errorf("generate %s identity: %w", prefix, err)
		}
		candidate := prefix + "_" + hex.EncodeToString(raw)
		if !service.idExistsLocked(candidate) {
			return candidate, nil
		}
	}
	return "", fmt.Errorf("generate %s identity: random source produced repeated identifiers", prefix)
}

func (service *UnifiedIdentityService) idExistsLocked(candidate string) bool {
	if _, ok := service.accounts[candidate]; ok {
		return true
	}
	if _, ok := service.principals[candidate]; ok {
		return true
	}
	if _, ok := service.credentials[candidate]; ok {
		return true
	}
	if _, ok := service.memberships[candidate]; ok {
		return true
	}
	if _, ok := service.mergePlans[candidate]; ok {
		return true
	}
	for _, event := range service.auditEvents {
		if event.EventID == candidate {
			return true
		}
	}
	return false
}

func (service *UnifiedIdentityService) appendAuditLocked(action, actorID, subjectType, subjectID, outcome string, details map[string]any, now time.Time) {
	previousHash := ""
	if len(service.auditEvents) > 0 {
		previousHash = service.auditEvents[len(service.auditEvents)-1].EventHash
	}
	eventID, err := service.newID("iaud")
	if err != nil {
		sum := sha256.Sum256([]byte(fmt.Sprintf("%s\x00%s\x00%d", action, subjectID, now.UnixNano())))
		eventID = "iaud_" + hex.EncodeToString(sum[:12])
	}
	event := IdentityAuditEventDTO{
		SchemaVersion: UnifiedIdentitySchemaVersion, EventID: eventID, Action: action,
		ActorPresent: strings.TrimSpace(actorID) != "", SubjectType: subjectType, SubjectID: subjectID,
		Outcome: outcome, Details: cloneIdentityDetails(details), PreviousHash: previousHash, CreatedAt: now,
	}
	hashPayload, hashErr := json.Marshal(struct {
		EventID      string         `json:"event_id"`
		Action       string         `json:"action"`
		ActorPresent bool           `json:"actor_present"`
		SubjectType  string         `json:"subject_type"`
		SubjectID    string         `json:"subject_id"`
		Outcome      string         `json:"outcome"`
		Details      map[string]any `json:"details,omitempty"`
		PreviousHash string         `json:"previous_hash,omitempty"`
		CreatedAtNS  int64          `json:"created_at_unix_ns"`
	}{
		EventID: event.EventID, Action: event.Action, ActorPresent: event.ActorPresent,
		SubjectType: event.SubjectType, SubjectID: event.SubjectID, Outcome: event.Outcome,
		Details: event.Details, PreviousHash: event.PreviousHash, CreatedAtNS: event.CreatedAt.UnixNano(),
	})
	if hashErr != nil {
		hashPayload = []byte(fmt.Sprintf("%s\x00%s\x00%s\x00%s\x00%s\x00%d",
			event.EventID, event.Action, event.SubjectType, event.SubjectID, event.PreviousHash, event.CreatedAt.UnixNano()))
	}
	event.EventHash = service.privateDigest(string(hashPayload))
	service.auditEvents = append(service.auditEvents, event)
}

func identityErrorCode(err error) string {
	var domainError IdentityDomainError
	if errors.As(err, &domainError) {
		return domainError.Code
	}
	return "identity_error"
}

func sortedIdentitySet(values map[string]struct{}) []string {
	result := make([]string, 0, len(values))
	for value := range values {
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func cloneIdentityDetails(details map[string]any) map[string]any {
	if len(details) == 0 {
		return nil
	}
	result := make(map[string]any, len(details))
	for key, value := range details {
		result[key] = value
	}
	return result
}

func cloneIdentityMergePlanDTO(plan IdentityMergePlanDTO) IdentityMergePlanDTO {
	plan.CredentialsToMove = append([]string(nil), plan.CredentialsToMove...)
	plan.MembershipsToMove = append([]string(nil), plan.MembershipsToMove...)
	plan.MembershipConflicts = append([]IdentityMergeConflictDTO(nil), plan.MembershipConflicts...)
	return plan
}
