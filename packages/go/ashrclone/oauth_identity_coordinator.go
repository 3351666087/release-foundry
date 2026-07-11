package ashrclone

import (
	"context"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"
)

// CompleteOAuthCallbackCommand contains only the verified identity and the
// provider connection that must become visible together.
type CompleteOAuthCallbackCommand struct {
	AccountID       string
	Provider        string
	ProviderSubject string
	ActorID         string
	Connection      OAuthConnection
}

type DisconnectOAuthCredentialCommand struct {
	AccountID    string
	ActorID      string
	Binding      OAuthSecretBinding
	Disconnected time.Time
}

type OAuthIdentityCoordinator interface {
	CompleteCallback(context.Context, CompleteOAuthCallbackCommand) (OAuthConnection, error)
	DisconnectCredential(context.Context, DisconnectOAuthCredentialCommand) (OAuthConnection, error)
}

// MemoryOAuthIdentityCoordinator is the transaction boundary for the in-memory
// canonical identity and provider connection stores. Callers must share the
// same Identity and Connections instances used by their OAuth service.
type MemoryOAuthIdentityCoordinator struct {
	mu          sync.Mutex
	identity    *UnifiedIdentityService
	connections *MemoryOAuthStore

	// afterIdentityMutation is intentionally private. Tests use it to prove
	// rollback after the first half of an in-memory transaction has changed.
	afterIdentityMutation func() error
}

func NewMemoryOAuthIdentityCoordinator(
	identity *UnifiedIdentityService,
	connections *MemoryOAuthStore,
) (*MemoryOAuthIdentityCoordinator, error) {
	if identity == nil || connections == nil {
		return nil, fmt.Errorf("memory OAuth identity coordinator requires identity and connection stores")
	}
	return &MemoryOAuthIdentityCoordinator{identity: identity, connections: connections}, nil
}

func (coordinator *MemoryOAuthIdentityCoordinator) CompleteCallback(
	_ context.Context,
	command CompleteOAuthCallbackCommand,
) (result OAuthConnection, err error) {
	coordinator.mu.Lock()
	defer coordinator.mu.Unlock()
	coordinator.identity.mu.Lock()
	defer coordinator.identity.mu.Unlock()
	coordinator.connections.mu.Lock()
	defer coordinator.connections.mu.Unlock()

	snapshot := coordinator.snapshotLocked()
	defer func() {
		if err != nil {
			coordinator.restoreLocked(snapshot)
		}
	}()

	accountID := strings.TrimSpace(command.AccountID)
	actorID := strings.TrimSpace(command.ActorID)
	provider, err := oauthIdentityProvider(command.Provider)
	if err != nil {
		return OAuthConnection{}, err
	}
	if strings.TrimSpace(command.ProviderSubject) == "" {
		return OAuthConnection{}, newOAuthPublicError(
			http.StatusBadGateway, "oauth_identity_invalid", "provider returned an invalid identity", nil,
		)
	}
	if err := validateCoordinatedConnection(
		command.Connection,
		accountID,
		string(provider),
		command.ProviderSubject,
	); err != nil {
		return OAuthConnection{}, err
	}

	account, err := coordinator.ensureAccountLocked(accountID, actorID)
	if err != nil {
		return OAuthConnection{}, oauthIdentityBridgeError(err)
	}
	now := coordinator.identity.now().UTC()
	credential, created, err := coordinator.identity.linkCredentialLockedWithStatus(
		account,
		IdentityCredentialInput{
			Kind:       IdentityCredentialOAuth,
			Provider:   provider,
			Identifier: command.ProviderSubject,
			Verified:   true,
		},
		actorID,
		now,
	)
	if err != nil {
		return OAuthConnection{}, oauthIdentityBridgeError(err)
	}
	coordinator.identity.appendAuditLocked(
		"identity.credential.link",
		actorID,
		"credential",
		credential.id,
		"success",
		map[string]any{
			"account_id":  accountID,
			"kind":        credential.kind,
			"provider":    credential.provider,
			"verified":    credential.verified,
			"created":     created,
			"coordinated": true,
		},
		now,
	)
	if coordinator.afterIdentityMutation != nil {
		if hookErr := coordinator.afterIdentityMutation(); hookErr != nil {
			return OAuthConnection{}, hookErr
		}
	}

	connection := command.Connection
	connection.AccountID = accountID
	connection.CredentialID = credential.id
	connection.Provider = string(provider)
	stored, err := coordinator.upsertConnectionLocked(connection)
	if err != nil {
		return OAuthConnection{}, err
	}
	return stored, nil
}

func (coordinator *MemoryOAuthIdentityCoordinator) DisconnectCredential(
	_ context.Context,
	command DisconnectOAuthCredentialCommand,
) (result OAuthConnection, err error) {
	coordinator.mu.Lock()
	defer coordinator.mu.Unlock()
	coordinator.identity.mu.Lock()
	defer coordinator.identity.mu.Unlock()
	coordinator.connections.mu.Lock()
	defer coordinator.connections.mu.Unlock()

	snapshot := coordinator.snapshotLocked()
	defer func() {
		if err != nil {
			coordinator.restoreLocked(snapshot)
		}
	}()

	accountID := strings.TrimSpace(command.AccountID)
	if accountID == "" || strings.TrimSpace(command.Binding.AccountID) != accountID {
		return OAuthConnection{}, newOAuthPublicError(
			http.StatusBadRequest, "invalid_oauth_binding", "OAuth account binding is invalid", nil,
		)
	}
	account, err := coordinator.identity.activeAccountLocked(accountID)
	if err != nil {
		return OAuthConnection{}, oauthIdentityBridgeError(err)
	}
	key := oauthBindingKey(command.Binding)
	connection, exists := coordinator.connections.connections[key]
	if !exists || connection.DisconnectedAt != nil {
		return OAuthConnection{}, newOAuthPublicError(
			http.StatusNotFound, "oauth_connection_not_found", "OAuth connection not found", ErrOAuthConnectionNotFound,
		)
	}
	credential, exists := coordinator.identity.credentials[connection.CredentialID]
	if !exists || credential.accountID != account.id {
		return OAuthConnection{}, oauthIdentityBridgeError(ErrIdentityCredentialNotFound)
	}
	if credential.canLogin && coordinator.identity.loginCredentialCountLocked(account) <= 1 {
		return OAuthConnection{}, oauthIdentityBridgeError(IdentityDomainError{
			Code: "last_login_credential", Message: "the final login-capable credential cannot be unlinked",
		})
	}

	disconnectedAt := command.Disconnected.UTC()
	if disconnectedAt.IsZero() {
		disconnectedAt = coordinator.identity.now().UTC()
	}
	connection.TokenRef = ""
	connection.DisconnectedAt = &disconnectedAt
	coordinator.connections.connections[key] = connection

	delete(account.credentialIDs, credential.id)
	delete(coordinator.identity.credentialOwners, credential.lookupDigest)
	delete(coordinator.identity.credentials, credential.id)
	account.revision++
	account.updatedAt = disconnectedAt
	coordinator.identity.appendAuditLocked(
		"identity.credential.unlink",
		command.ActorID,
		"credential",
		credential.id,
		"success",
		map[string]any{
			"account_id":  account.id,
			"kind":        credential.kind,
			"provider":    credential.provider,
			"coordinated": true,
		},
		disconnectedAt,
	)
	if coordinator.afterIdentityMutation != nil {
		if hookErr := coordinator.afterIdentityMutation(); hookErr != nil {
			return OAuthConnection{}, hookErr
		}
	}
	return connection, nil
}

func validateCoordinatedConnection(connection OAuthConnection, accountID, provider, providerSubject string) error {
	expectedSubjectHash := oauthProviderSubjectSHA256(provider, providerSubject)
	if strings.TrimSpace(accountID) == "" ||
		strings.TrimSpace(connection.AccountID) != accountID ||
		!strings.EqualFold(strings.TrimSpace(connection.Provider), provider) ||
		!strings.EqualFold(strings.TrimSpace(connection.ProviderSubjectHash), expectedSubjectHash) {
		return newOAuthPublicError(
			http.StatusBadRequest,
			"invalid_oauth_connection",
			"verified OAuth connection does not match the canonical identity command",
			nil,
		)
	}
	return nil
}

func (coordinator *MemoryOAuthIdentityCoordinator) ensureAccountLocked(
	accountID string,
	actorID string,
) (*identityAccount, error) {
	accountID = strings.TrimSpace(accountID)
	if accountID == "" || len(accountID) > 256 || strings.ContainsAny(accountID, " \t\r\n/") {
		return nil, IdentityDomainError{Code: "invalid_account_id", Message: "canonical account_id is invalid"}
	}
	if existing, exists := coordinator.identity.accounts[accountID]; exists {
		if existing.status != "active" {
			return nil, IdentityDomainError{Code: "identity_account_inactive", Message: "identity account is not active"}
		}
		return existing, nil
	}
	principalID, err := coordinator.identity.newID("prn")
	if err != nil {
		return nil, err
	}
	now := coordinator.identity.now().UTC()
	account := &identityAccount{
		id:            accountID,
		primaryID:     principalID,
		status:        "active",
		credentialIDs: make(map[string]struct{}),
		membershipIDs: make(map[string]struct{}),
		revision:      1,
		createdAt:     now,
		updatedAt:     now,
	}
	coordinator.identity.accounts[accountID] = account
	coordinator.identity.principals[principalID] = &identityPrincipal{
		id: principalID, accountID: accountID, status: "active", createdAt: now,
	}
	coordinator.identity.appendAuditLocked(
		"identity.account.ensured",
		actorID,
		"account",
		accountID,
		"success",
		map[string]any{"trusted_external_account_id": true, "coordinated": true},
		now,
	)
	return account, nil
}

func (coordinator *MemoryOAuthIdentityCoordinator) upsertConnectionLocked(
	connection OAuthConnection,
) (OAuthConnection, error) {
	subjectKey := strings.ToLower(strings.TrimSpace(connection.Provider)) + ":" + connection.ProviderSubjectHash
	if owner, exists := coordinator.connections.subjectOwners[subjectKey]; exists && owner != connection.AccountID {
		return OAuthConnection{}, newOAuthPublicError(
			http.StatusConflict,
			"credential_link_conflict",
			"verified provider credential is already linked to another account",
			nil,
		)
	}
	key := oauthBindingKey(OAuthSecretBinding{
		Provider: connection.Provider, TenantID: connection.TenantID, ProjectID: connection.ProjectID,
		SessionID: connection.SessionID, UserID: connection.UserID, AccountID: connection.AccountID,
	})
	if previous, exists := coordinator.connections.connections[key]; exists &&
		previous.TokenRef != "" && previous.TokenRef != connection.TokenRef {
		delete(coordinator.connections.secrets, previous.TokenRef)
	}
	coordinator.connections.subjectOwners[subjectKey] = connection.AccountID
	coordinator.connections.connections[key] = connection
	return connection, nil
}

type memoryOAuthIdentitySnapshot struct {
	accounts         map[string]*identityAccount
	principals       map[string]*identityPrincipal
	credentials      map[string]*identityCredential
	credentialOwners map[string]string
	memberships      map[string]*identityMembership
	mergePlans       map[string]*identityMergePlan
	auditEvents      []IdentityAuditEventDTO
	secrets          map[string]string
	connections      map[string]OAuthConnection
	subjectOwners    map[string]string
}

func (coordinator *MemoryOAuthIdentityCoordinator) snapshotLocked() memoryOAuthIdentitySnapshot {
	return memoryOAuthIdentitySnapshot{
		accounts:         cloneIdentityAccounts(coordinator.identity.accounts),
		principals:       cloneIdentityPrincipals(coordinator.identity.principals),
		credentials:      cloneIdentityCredentials(coordinator.identity.credentials),
		credentialOwners: cloneStringStringMap(coordinator.identity.credentialOwners),
		memberships:      cloneIdentityMemberships(coordinator.identity.memberships),
		mergePlans:       cloneIdentityMergePlans(coordinator.identity.mergePlans),
		auditEvents:      cloneIdentityAuditEvents(coordinator.identity.auditEvents),
		secrets:          cloneStringStringMap(coordinator.connections.secrets),
		connections:      cloneOAuthConnections(coordinator.connections.connections),
		subjectOwners:    cloneStringStringMap(coordinator.connections.subjectOwners),
	}
}

func (coordinator *MemoryOAuthIdentityCoordinator) restoreLocked(snapshot memoryOAuthIdentitySnapshot) {
	coordinator.identity.accounts = snapshot.accounts
	coordinator.identity.principals = snapshot.principals
	coordinator.identity.credentials = snapshot.credentials
	coordinator.identity.credentialOwners = snapshot.credentialOwners
	coordinator.identity.memberships = snapshot.memberships
	coordinator.identity.mergePlans = snapshot.mergePlans
	coordinator.identity.auditEvents = snapshot.auditEvents
	coordinator.connections.secrets = snapshot.secrets
	coordinator.connections.connections = snapshot.connections
	coordinator.connections.subjectOwners = snapshot.subjectOwners
}

func cloneIdentityAccounts(source map[string]*identityAccount) map[string]*identityAccount {
	result := make(map[string]*identityAccount, len(source))
	for key, value := range source {
		cloned := *value
		cloned.credentialIDs = cloneStringSet(value.credentialIDs)
		cloned.membershipIDs = cloneStringSet(value.membershipIDs)
		result[key] = &cloned
	}
	return result
}

func cloneIdentityPrincipals(source map[string]*identityPrincipal) map[string]*identityPrincipal {
	result := make(map[string]*identityPrincipal, len(source))
	for key, value := range source {
		cloned := *value
		result[key] = &cloned
	}
	return result
}

func cloneIdentityCredentials(source map[string]*identityCredential) map[string]*identityCredential {
	result := make(map[string]*identityCredential, len(source))
	for key, value := range source {
		cloned := *value
		if value.lastUsedAt != nil {
			lastUsedAt := *value.lastUsedAt
			cloned.lastUsedAt = &lastUsedAt
		}
		result[key] = &cloned
	}
	return result
}

func cloneIdentityMemberships(source map[string]*identityMembership) map[string]*identityMembership {
	result := make(map[string]*identityMembership, len(source))
	for key, value := range source {
		cloned := *value
		result[key] = &cloned
	}
	return result
}

func cloneIdentityMergePlans(source map[string]*identityMergePlan) map[string]*identityMergePlan {
	result := make(map[string]*identityMergePlan, len(source))
	for key, value := range source {
		cloned := *value
		cloned.dto = cloneIdentityMergePlanDTO(value.dto)
		result[key] = &cloned
	}
	return result
}

func cloneIdentityAuditEvents(source []IdentityAuditEventDTO) []IdentityAuditEventDTO {
	result := make([]IdentityAuditEventDTO, len(source))
	for index, value := range source {
		result[index] = value
		result[index].Details = cloneIdentityDetails(value.Details)
	}
	return result
}

func cloneOAuthConnections(source map[string]OAuthConnection) map[string]OAuthConnection {
	result := make(map[string]OAuthConnection, len(source))
	for key, value := range source {
		cloned := value
		if value.DisconnectedAt != nil {
			disconnectedAt := *value.DisconnectedAt
			cloned.DisconnectedAt = &disconnectedAt
		}
		result[key] = cloned
	}
	return result
}

func cloneStringStringMap(source map[string]string) map[string]string {
	result := make(map[string]string, len(source))
	for key, value := range source {
		result[key] = value
	}
	return result
}

func cloneStringSet(source map[string]struct{}) map[string]struct{} {
	result := make(map[string]struct{}, len(source))
	for key := range source {
		result[key] = struct{}{}
	}
	return result
}
