package ashrclone

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// IdentityHTTPSession is trusted server-side authentication context. AccountID
// is authoritative; an account ID in a URL is only an ownership assertion.
type IdentityHTTPSession struct {
	AccountID string
	ActorID   string
	SessionID string
	Revoked   bool
}

type IdentityHTTPSessionResolver interface {
	ResolveIdentityHTTPSession(context.Context, *http.Request) (IdentityHTTPSession, error)
}

var (
	ErrIdentitySessionRefreshInvalid = errors.New("identity session refresh is unavailable")
	ErrIdentitySessionRefreshReused  = errors.New("identity session refresh credential was reused")
)

type IdentityHTTPSessionRefresher interface {
	RefreshIdentityHTTPSession(
		context.Context,
		*http.Request,
		string,
		string,
		string,
	) (IdentitySessionIssuanceReceipt, error)
}

// UnifiedIdentityHTTPStore is the production HTTP read boundary. A durable
// control-plane backend can implement it without exposing a memory service.
type UnifiedIdentityHTTPStore interface {
	GetIdentityAccount(context.Context, string) (IdentityAccountDTO, error)
}

// LocalhostDevIdentityHTTPSessionResolver is intentionally limited to direct
// loopback requests and fixed server configuration. It never reads identity
// ownership from request headers, query parameters, or bodies.
type LocalhostDevIdentityHTTPSessionResolver struct {
	Enabled   bool
	AccountID string
	ActorID   string
	SessionID string
	Revoked   func(context.Context, string) (bool, error)
}

func (resolver LocalhostDevIdentityHTTPSessionResolver) ResolveIdentityHTTPSession(_ context.Context, request *http.Request) (IdentityHTTPSession, error) {
	if !resolver.Enabled {
		return IdentityHTTPSession{}, fmt.Errorf("localhost identity session resolver is disabled")
	}
	if request == nil || !isLoopbackRequest(request) {
		return IdentityHTTPSession{}, fmt.Errorf("localhost identity session resolver rejected a non-loopback request")
	}
	session := IdentityHTTPSession{
		AccountID: strings.TrimSpace(resolver.AccountID),
		ActorID:   strings.TrimSpace(resolver.ActorID),
		SessionID: strings.TrimSpace(resolver.SessionID),
	}
	if session.AccountID == "" || session.ActorID == "" || session.SessionID == "" {
		return IdentityHTTPSession{}, fmt.Errorf("localhost identity session is incomplete")
	}
	if resolver.Revoked != nil {
		revoked, err := resolver.Revoked(request.Context(), session.SessionID)
		if err != nil {
			return IdentityHTTPSession{}, fmt.Errorf("localhost identity session status is unavailable")
		}
		session.Revoked = revoked
	}
	return session, nil
}

func (server *HTTPServer) handleUnifiedIdentityAccount(writer http.ResponseWriter, request *http.Request, assertedAccountID string, parts []string) {
	writer.Header().Set("Cache-Control", "no-store")
	writer.Header().Set("Pragma", "no-cache")
	writer.Header().Set("X-Content-Type-Options", "nosniff")
	session, ok := server.resolveIdentityHTTPSession(writer, request, assertedAccountID)
	if !ok {
		return
	}
	if len(parts) >= 1 && (parts[0] == "security" || parts[0] == "password" || parts[0] == "two-factor") {
		server.handleIdentitySecurity(writer, request, session, parts)
		return
	}
	identity := server.unifiedIdentityHTTPStore()
	if identity == nil {
		writeError(writer, http.StatusNotFound, "not_found", "route not found")
		return
	}

	switch {
	case len(parts) == 0:
		if request.Method != http.MethodGet {
			writeError(writer, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
			return
		}
		account, err := identity.GetIdentityAccount(request.Context(), session.AccountID)
		writeIdentityHTTPResult(writer, publicIdentityAccount(account), err)
	case len(parts) == 1 && parts[0] == "credentials":
		if request.Method != http.MethodGet {
			writeError(writer, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
			return
		}
		account, err := identity.GetIdentityAccount(request.Context(), session.AccountID)
		if err != nil {
			writeIdentityHTTPError(writer, err)
			return
		}
		writeJSON(writer, http.StatusOK, JSONMap{
			"schema_version": UnifiedIdentitySchemaVersion,
			"account_id":     account.AccountID,
			"credentials":    publicIdentityCredentials(account.Credentials),
			"count":          account.CredentialCount,
		})
	case len(parts) == 1 && parts[0] == "memberships":
		if request.Method != http.MethodGet {
			writeError(writer, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
			return
		}
		account, err := identity.GetIdentityAccount(request.Context(), session.AccountID)
		if err != nil {
			writeIdentityHTTPError(writer, err)
			return
		}
		writeJSON(writer, http.StatusOK, JSONMap{
			"schema_version": UnifiedIdentitySchemaVersion,
			"account_id":     account.AccountID,
			"memberships":    publicIdentityMemberships(account.Memberships),
			"count":          account.MembershipCount,
		})
	// Route contracts:
	// POST /v1/accounts/{account_id}/credentials/{provider}/link
	// DELETE /v1/accounts/{account_id}/credentials/{credential_id}/unlink
	//
	// These mutations remain fail-closed until the HTTP boundary receives a
	// provider-verified assertion/link ticket. Raw identifiers in a request
	// must never be accepted as proof of credential ownership.
	case len(parts) == 3 && parts[0] == "credentials" && (parts[2] == "link" || parts[2] == "unlink"):
		writeError(writer, http.StatusMethodNotAllowed, "identity_mutation_requires_verified_assertion", "identity credential mutations require a verified server-side assertion")
	default:
		writeError(writer, http.StatusNotFound, "not_found", "route not found")
	}
}

func (server *HTTPServer) unifiedIdentityHTTPStore() UnifiedIdentityHTTPStore {
	if identity, ok := server.service.(UnifiedIdentityHTTPStore); ok && identity != nil {
		return identity
	}
	if server.identityVerification != nil && server.identityVerification.identity != nil {
		return identityVerificationHTTPStoreAdapter{store: server.identityVerification.identity}
	}
	if server.unifiedIdentity != nil {
		return unifiedIdentityHTTPServiceAdapter{service: server.unifiedIdentity}
	}
	return nil
}

type identityVerificationHTTPStoreAdapter struct {
	store IdentityVerificationIdentityStore
}

func (adapter identityVerificationHTTPStoreAdapter) GetIdentityAccount(
	ctx context.Context,
	accountID string,
) (IdentityAccountDTO, error) {
	return adapter.store.GetAccount(ctx, accountID)
}

type unifiedIdentityHTTPServiceAdapter struct {
	service *UnifiedIdentityService
}

func (adapter unifiedIdentityHTTPServiceAdapter) GetIdentityAccount(
	_ context.Context,
	accountID string,
) (IdentityAccountDTO, error) {
	return adapter.service.GetAccount(accountID)
}

func (server *HTTPServer) resolveIdentityHTTPSession(writer http.ResponseWriter, request *http.Request, assertedAccountID string) (IdentityHTTPSession, bool) {
	if server.identitySessions == nil {
		writeError(writer, http.StatusUnauthorized, "identity_session_required", "a trusted identity session is required")
		return IdentityHTTPSession{}, false
	}
	if identitySessionCookiePresent(request, IdentitySessionCookieName) {
		if server.identitySessionReceiptTransport == nil ||
			server.identitySessionReceiptTransport.ValidateIdentitySessionRequest(request) != nil {
			writeError(writer, http.StatusUnauthorized, "identity_session_invalid", "identity session could not be authenticated")
			return IdentityHTTPSession{}, false
		}
	}
	session, err := server.identitySessions.ResolveIdentityHTTPSession(request.Context(), request)
	if err != nil {
		writeError(writer, http.StatusUnauthorized, "identity_session_invalid", "identity session could not be authenticated")
		return IdentityHTTPSession{}, false
	}
	session.AccountID = strings.TrimSpace(session.AccountID)
	session.ActorID = strings.TrimSpace(session.ActorID)
	session.SessionID = strings.TrimSpace(session.SessionID)
	if session.Revoked || session.AccountID == "" || session.ActorID == "" || session.SessionID == "" {
		writeError(writer, http.StatusUnauthorized, "identity_session_invalid", "identity session could not be authenticated")
		return IdentityHTTPSession{}, false
	}
	if strings.TrimSpace(assertedAccountID) == "" || strings.TrimSpace(assertedAccountID) != session.AccountID {
		writeError(writer, http.StatusForbidden, "account_mismatch", "account_id does not match the authenticated account")
		return IdentityHTTPSession{}, false
	}
	return session, true
}

func identitySessionCookiePresent(request *http.Request, name string) bool {
	if request == nil {
		return false
	}
	for _, cookie := range request.Cookies() {
		if cookie.Name == name {
			return true
		}
	}
	return false
}

type publicIdentityAccountView struct {
	SchemaVersion   string                         `json:"schema_version"`
	AccountID       string                         `json:"account_id"`
	PrimaryID       string                         `json:"primary_principal_id"`
	DisplayName     string                         `json:"display_name,omitempty"`
	Status          string                         `json:"status"`
	Credentials     []publicIdentityCredentialView `json:"credentials"`
	Memberships     []publicIdentityMembershipView `json:"memberships"`
	CredentialCount int                            `json:"credential_count"`
	MembershipCount int                            `json:"membership_count"`
	SecurityPosture IdentitySecurityPostureDTO     `json:"security_posture"`
	CreatedAt       time.Time                      `json:"created_at"`
	UpdatedAt       time.Time                      `json:"updated_at"`
}

type publicIdentityCredentialView struct {
	SchemaVersion string                 `json:"schema_version"`
	CredentialID  string                 `json:"credential_id"`
	Kind          IdentityCredentialKind `json:"kind"`
	Provider      IdentityProvider       `json:"provider"`
	Verified      bool                   `json:"verified"`
	CanLogin      bool                   `json:"can_login"`
	LinkedAt      time.Time              `json:"linked_at"`
	LastUsedAt    *time.Time             `json:"last_used_at,omitempty"`
}

type publicIdentityMembershipView struct {
	SchemaVersion string    `json:"schema_version"`
	MembershipID  string    `json:"membership_id"`
	AccountID     string    `json:"account_id"`
	TenantID      string    `json:"tenant_id"`
	ProjectID     string    `json:"project_id,omitempty"`
	Role          string    `json:"role"`
	CreatedAt     time.Time `json:"created_at"`
	UpdatedAt     time.Time `json:"updated_at"`
}

func publicIdentityAccount(account IdentityAccountDTO) publicIdentityAccountView {
	return publicIdentityAccountView{
		SchemaVersion:   account.SchemaVersion,
		AccountID:       account.AccountID,
		PrimaryID:       account.PrimaryID,
		DisplayName:     account.DisplayName,
		Status:          account.Status,
		Credentials:     publicIdentityCredentials(account.Credentials),
		Memberships:     publicIdentityMemberships(account.Memberships),
		CredentialCount: account.CredentialCount,
		MembershipCount: account.MembershipCount,
		SecurityPosture: account.SecurityPosture,
		CreatedAt:       account.CreatedAt,
		UpdatedAt:       account.UpdatedAt,
	}
}

func publicIdentityCredentials(credentials []IdentityCredentialDTO) []publicIdentityCredentialView {
	result := make([]publicIdentityCredentialView, 0, len(credentials))
	for _, credential := range credentials {
		result = append(result, publicIdentityCredentialView{
			SchemaVersion: credential.SchemaVersion,
			CredentialID:  credential.CredentialID,
			Kind:          credential.Kind,
			Provider:      credential.Provider,
			Verified:      credential.Verified,
			CanLogin:      credential.CanLogin,
			LinkedAt:      credential.LinkedAt,
			LastUsedAt:    credential.LastUsedAt,
		})
	}
	return result
}

func publicIdentityMemberships(memberships []IdentityMembershipDTO) []publicIdentityMembershipView {
	result := make([]publicIdentityMembershipView, 0, len(memberships))
	for _, membership := range memberships {
		result = append(result, publicIdentityMembershipView{
			SchemaVersion: membership.SchemaVersion,
			MembershipID:  membership.MembershipID,
			AccountID:     membership.AccountID,
			TenantID:      membership.TenantID,
			ProjectID:     membership.ProjectID,
			Role:          membership.Role,
			CreatedAt:     membership.CreatedAt,
			UpdatedAt:     membership.UpdatedAt,
		})
	}
	return result
}

func writeIdentityHTTPResult(writer http.ResponseWriter, result publicIdentityAccountView, err error) {
	if err != nil {
		writeIdentityHTTPError(writer, err)
		return
	}
	writeJSON(writer, http.StatusOK, result)
}

func writeIdentityHTTPError(writer http.ResponseWriter, err error) {
	var domainError IdentityDomainError
	switch {
	case errors.Is(err, ErrIdentityAccountNotFound):
		writeError(writer, http.StatusNotFound, "identity_account_not_found", "identity account not found")
	case errors.As(err, &domainError):
		writeError(writer, http.StatusBadRequest, domainError.Code, domainError.Error())
	default:
		writeError(writer, http.StatusInternalServerError, "identity_service_error", "identity service request failed")
	}
}
