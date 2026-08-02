package releasefoundry

import (
	"context"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"
)

type CompleteGitHubOAuthCallbackCommand struct {
	AccountID       string
	ProviderSubject string
	ActorID         string
	Connection      GitHubOAuthConnection
}

type DisconnectGitHubOAuthCredentialCommand struct {
	AccountID    string
	ActorID      string
	Binding      GitHubOAuthSecretBinding
	Disconnected time.Time
}

type GitHubOAuthIdentityCoordinator interface {
	CompleteCallback(context.Context, CompleteGitHubOAuthCallbackCommand) (GitHubOAuthConnection, error)
	DisconnectCredential(context.Context, DisconnectGitHubOAuthCredentialCommand) (GitHubOAuthConnection, error)
}

type MemoryGitHubOAuthIdentityCoordinator struct {
	mu          sync.Mutex
	identity    *UnifiedIdentityService
	connections *MemoryGitHubOAuthStore
}

func NewMemoryGitHubOAuthIdentityCoordinator(
	identity *UnifiedIdentityService,
	connections *MemoryGitHubOAuthStore,
) (*MemoryGitHubOAuthIdentityCoordinator, error) {
	if identity == nil || connections == nil {
		return nil, fmt.Errorf("memory GitHub OAuth identity coordinator requires identity and connection stores")
	}
	return &MemoryGitHubOAuthIdentityCoordinator{identity: identity, connections: connections}, nil
}

func (coordinator *MemoryGitHubOAuthIdentityCoordinator) CompleteCallback(
	_ context.Context,
	command CompleteGitHubOAuthCallbackCommand,
) (result GitHubOAuthConnection, err error) {
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
	subject := strings.TrimSpace(command.ProviderSubject)
	if subject == "" {
		return GitHubOAuthConnection{}, oauthPublicError(
			http.StatusBadGateway, "oauth_identity_invalid", "provider returned an invalid identity", nil,
		)
	}
	if command.Connection.AccountID != accountID ||
		!strings.EqualFold(command.Connection.ProviderSubjectHash, oauthProviderSubjectSHA256("github", subject)) {
		return GitHubOAuthConnection{}, oauthPublicError(
			http.StatusBadRequest, "invalid_oauth_connection",
			"verified OAuth connection does not match the canonical identity command", nil,
		)
	}
	account, err := ensureIdentityAccountLocked(coordinator.identity, accountID, command.ActorID)
	if err != nil {
		return GitHubOAuthConnection{}, githubOAuthErrorFromOAuthError(oauthIdentityBridgeError(err))
	}
	now := coordinator.identity.now().UTC()
	credential, created, err := coordinator.identity.linkCredentialLockedWithStatus(
		account,
		IdentityCredentialInput{
			Kind: IdentityCredentialOAuth, Provider: IdentityProviderGitHub,
			Identifier: subject, Verified: true,
		},
		command.ActorID,
		now,
	)
	if err != nil {
		return GitHubOAuthConnection{}, githubOAuthErrorFromOAuthError(oauthIdentityBridgeError(err))
	}
	coordinator.identity.appendAuditLocked(
		"identity.credential.link", command.ActorID, "credential", credential.id, "success",
		map[string]any{
			"account_id": accountID, "kind": credential.kind, "provider": credential.provider,
			"verified": credential.verified, "created": created, "coordinated": true,
		},
		now,
	)

	connection := command.Connection
	connection.CredentialID = credential.id
	subjectKey := "github:" + strings.ToLower(strings.TrimSpace(connection.ProviderSubjectHash))
	if owner, exists := coordinator.connections.subjectOwners[subjectKey]; exists && owner != accountID {
		return GitHubOAuthConnection{}, GitHubOAuthError{
			Status: http.StatusConflict, Code: "credential_link_conflict",
			Message: "verified provider credential is already linked to another account",
		}
	}
	key := githubOAuthBindingKey(GitHubOAuthSecretBinding{
		TenantID: connection.TenantID, ProjectID: connection.ProjectID, SessionID: connection.SessionID,
		UserID: connection.UserID, AccountID: connection.AccountID,
	})
	if previous, exists := coordinator.connections.connections[key]; exists &&
		previous.TokenRef != "" && previous.TokenRef != connection.TokenRef {
		delete(coordinator.connections.secrets, previous.TokenRef)
	}
	coordinator.connections.subjectOwners[subjectKey] = accountID
	coordinator.connections.connections[key] = connection
	return connection, nil
}

func (coordinator *MemoryGitHubOAuthIdentityCoordinator) DisconnectCredential(
	_ context.Context,
	command DisconnectGitHubOAuthCredentialCommand,
) (result GitHubOAuthConnection, err error) {
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
	if accountID == "" || command.Binding.AccountID != accountID {
		return GitHubOAuthConnection{}, oauthPublicError(
			http.StatusBadRequest, "invalid_oauth_binding", "OAuth account binding is invalid", nil,
		)
	}
	account, err := coordinator.identity.activeAccountLocked(accountID)
	if err != nil {
		return GitHubOAuthConnection{}, githubOAuthErrorFromOAuthError(oauthIdentityBridgeError(err))
	}
	key := githubOAuthBindingKey(command.Binding)
	connection, exists := coordinator.connections.connections[key]
	if !exists || connection.DisconnectedAt != nil {
		return GitHubOAuthConnection{}, oauthPublicError(
			http.StatusNotFound, "oauth_connection_not_found", "GitHub connection not found", ErrGitHubOAuthConnectionNotFound,
		)
	}
	credential, exists := coordinator.identity.credentials[connection.CredentialID]
	if !exists || credential.accountID != account.id {
		return GitHubOAuthConnection{}, githubOAuthErrorFromOAuthError(oauthIdentityBridgeError(ErrIdentityCredentialNotFound))
	}
	if credential.canLogin && coordinator.identity.loginCredentialCountLocked(account) <= 1 {
		return GitHubOAuthConnection{}, githubOAuthErrorFromOAuthError(oauthIdentityBridgeError(IdentityDomainError{
			Code: "last_login_credential", Message: "the final login-capable credential cannot be unlinked",
		}))
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
		"identity.credential.unlink", command.ActorID, "credential", credential.id, "success",
		map[string]any{
			"account_id": account.id, "kind": credential.kind, "provider": credential.provider,
			"coordinated": true,
		},
		disconnectedAt,
	)
	return connection, nil
}

type memoryGitHubOAuthIdentitySnapshot struct {
	identity    memoryOAuthIdentitySnapshot
	secrets     map[string]string
	connections map[string]GitHubOAuthConnection
	owners      map[string]string
}

func (coordinator *MemoryGitHubOAuthIdentityCoordinator) snapshotLocked() memoryGitHubOAuthIdentitySnapshot {
	return memoryGitHubOAuthIdentitySnapshot{
		identity: memoryOAuthIdentitySnapshot{
			accounts: cloneIdentityAccounts(coordinator.identity.accounts), principals: cloneIdentityPrincipals(coordinator.identity.principals),
			credentials: cloneIdentityCredentials(coordinator.identity.credentials), credentialOwners: cloneStringStringMap(coordinator.identity.credentialOwners),
			memberships: cloneIdentityMemberships(coordinator.identity.memberships), mergePlans: cloneIdentityMergePlans(coordinator.identity.mergePlans),
			auditEvents: cloneIdentityAuditEvents(coordinator.identity.auditEvents),
		},
		secrets:     cloneStringStringMap(coordinator.connections.secrets),
		connections: cloneGitHubOAuthConnections(coordinator.connections.connections),
		owners:      cloneStringStringMap(coordinator.connections.subjectOwners),
	}
}

func (coordinator *MemoryGitHubOAuthIdentityCoordinator) restoreLocked(snapshot memoryGitHubOAuthIdentitySnapshot) {
	coordinator.identity.accounts = snapshot.identity.accounts
	coordinator.identity.principals = snapshot.identity.principals
	coordinator.identity.credentials = snapshot.identity.credentials
	coordinator.identity.credentialOwners = snapshot.identity.credentialOwners
	coordinator.identity.memberships = snapshot.identity.memberships
	coordinator.identity.mergePlans = snapshot.identity.mergePlans
	coordinator.identity.auditEvents = snapshot.identity.auditEvents
	coordinator.connections.secrets = snapshot.secrets
	coordinator.connections.connections = snapshot.connections
	coordinator.connections.subjectOwners = snapshot.owners
}

func cloneGitHubOAuthConnections(source map[string]GitHubOAuthConnection) map[string]GitHubOAuthConnection {
	result := make(map[string]GitHubOAuthConnection, len(source))
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

func ensureIdentityAccountLocked(
	identity *UnifiedIdentityService,
	accountID string,
	actorID string,
) (*identityAccount, error) {
	accountID = strings.TrimSpace(accountID)
	if accountID == "" || len(accountID) > 256 || strings.ContainsAny(accountID, " \t\r\n/") {
		return nil, IdentityDomainError{Code: "invalid_account_id", Message: "canonical account_id is invalid"}
	}
	if existing, exists := identity.accounts[accountID]; exists {
		if existing.status != "active" {
			return nil, IdentityDomainError{Code: "identity_account_inactive", Message: "identity account is not active"}
		}
		return existing, nil
	}
	principalID, err := identity.newID("prn")
	if err != nil {
		return nil, err
	}
	now := identity.now().UTC()
	account := &identityAccount{
		id: accountID, primaryID: principalID, status: "active",
		credentialIDs: make(map[string]struct{}), membershipIDs: make(map[string]struct{}),
		revision: 1, createdAt: now, updatedAt: now,
	}
	identity.accounts[accountID] = account
	identity.principals[principalID] = &identityPrincipal{
		id: principalID, accountID: accountID, status: "active", createdAt: now,
	}
	identity.appendAuditLocked(
		"identity.account.ensured", actorID, "account", accountID, "success",
		map[string]any{"trusted_external_account_id": true, "coordinated": true}, now,
	)
	return account, nil
}

func githubOAuthProviderSubject(userID int64) string {
	return strconv.FormatInt(userID, 10)
}
