package releasefoundry

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"time"
)

const IdentitySecurityHTTPSchemaVersion = "releasefoundry.identity_security_http.v1"

var ErrIdentitySecurityUnavailable = errors.New("identity security mutation unavailable")
var ErrIdentitySecurityRejected = errors.New("identity security mutation rejected")

type IdentitySecurityHTTPPostureDTO struct {
	SchemaVersion             string `json:"schema_version"`
	PasswordStatus            string `json:"password_status"`
	PasswordChangeAvailable   bool   `json:"password_change_available"`
	PasswordRecoveryAvailable bool   `json:"password_recovery_available"`
	TwoFactorStatus           string `json:"two_factor_status"`
	TwoFactorOptional         bool   `json:"two_factor_optional"`
	TwoFactorRecommended      bool   `json:"two_factor_recommended"`
	RecoveryCodesRemaining    int    `json:"recovery_codes_remaining"`
	SecurityVersion           int64  `json:"security_version"`
	ActiveSessions            int64  `json:"active_sessions"`
}

type IdentitySecurityHTTPMutationResultDTO struct {
	SchemaVersion            string `json:"schema_version"`
	PasswordStatus           string `json:"password_status,omitempty"`
	TwoFactorStatus          string `json:"two_factor_status,omitempty"`
	ConfirmationRequired     bool   `json:"confirmation_required,omitempty"`
	RecoveryCodesRemaining   int    `json:"recovery_codes_remaining,omitempty"`
	SecurityVersion          int64  `json:"security_version,omitempty"`
	SessionsRevoked          int64  `json:"sessions_revoked"`
	ReauthenticationRequired bool   `json:"reauthentication_required,omitempty"`
}

// IdentitySecurityMutationTicket is resolved exclusively by trusted server-side
// infrastructure. Its secret material must never be serialized to a client.
type IdentitySecurityMutationTicket struct {
	TicketID            string
	AccountID           string
	Operation           string
	SecretRef           string
	SecretDigest        string
	ReceiptDigest       string
	ContextDigest       string
	RecoveryBatchDigest string
	RecoveryCodeCount   int
	ExpiresAt           time.Time
}

type IdentitySecurityTicketResolver interface {
	ResolveIdentitySecurityMutationTicket(context.Context, string, string, string, string) (IdentitySecurityMutationTicket, error)
}

type IdentitySecurityMutation struct {
	AccountID      string
	ActorID        string
	SessionID      string
	Operation      string
	IdempotencyKey string
	Ticket         IdentitySecurityMutationTicket
}

type IdentitySecurityHTTPStore interface {
	GetIdentitySecurityPosture(context.Context, string) (IdentitySecurityHTTPPostureDTO, error)
	MutateIdentitySecurity(context.Context, IdentitySecurityMutation) (IdentitySecurityHTTPMutationResultDTO, error)
}

func (server *HTTPServer) handleIdentitySecurity(w http.ResponseWriter, r *http.Request, session IdentityHTTPSession, parts []string) {
	if server.identitySecurity == nil {
		writeError(w, http.StatusServiceUnavailable, "identity_security_unavailable", "identity security capability is unavailable")
		return
	}
	if len(parts) == 1 && parts[0] == "security" {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
			return
		}
		posture, err := server.identitySecurity.GetIdentitySecurityPosture(r.Context(), session.AccountID)
		if err != nil {
			writeError(w, http.StatusServiceUnavailable, "identity_security_unavailable", "identity security capability is unavailable")
			return
		}
		posture.SchemaVersion = IdentitySecurityHTTPSchemaVersion
		writeJSON(w, http.StatusOK, posture)
		return
	}
	operation, ok := identitySecurityOperation(parts)
	if !ok || r.Method != http.MethodPost {
		writeError(w, http.StatusNotFound, "not_found", "route not found")
		return
	}
	if server.identitySecurityTickets == nil {
		writeError(w, http.StatusServiceUnavailable, "identity_security_unavailable", "identity security capability is unavailable")
		return
	}
	body, ok := readJSONBody(w, r)
	if !ok {
		return
	}
	if validateIdentitySecurityBody(body) != nil {
		writeError(w, http.StatusBadRequest, "secret_input_rejected", "security mutations accept opaque server-issued identifiers only")
		return
	}
	ticketID := stringValue(body, "mutation_ticket_id")
	stepUpID := stringValue(body, "step_up_receipt_id")
	bodyKey := stringValue(body, "idempotency_key")
	headerKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if headerKey == "" || bodyKey == "" || headerKey != bodyKey ||
		!validIdentitySecurityIdempotencyKey(headerKey) ||
		ticketID == "" || stepUpID == "" {
		writeError(w, http.StatusBadRequest, "invalid_security_mutation", "mutation ticket, step-up receipt, and matching idempotency key are required")
		return
	}
	ticket, err := server.identitySecurityTickets.ResolveIdentitySecurityMutationTicket(
		r.Context(), session.AccountID, ticketID, stepUpID, operation,
	)
	if err != nil || ticket.AccountID != session.AccountID || ticket.Operation != operation {
		writeError(w, http.StatusForbidden, "identity_security_mutation_rejected", "identity security mutation could not be authorized")
		return
	}
	result, err := server.identitySecurity.MutateIdentitySecurity(r.Context(), IdentitySecurityMutation{
		AccountID: session.AccountID, ActorID: session.ActorID, SessionID: session.SessionID,
		Operation: operation, IdempotencyKey: headerKey, Ticket: ticket,
	})
	if err != nil {
		if errors.Is(err, ErrIdentitySecurityUnavailable) {
			writeError(w, http.StatusServiceUnavailable, "identity_security_unavailable", "identity security capability is unavailable")
			return
		}
		writeError(w, http.StatusForbidden, "identity_security_mutation_rejected", "identity security mutation could not be completed")
		return
	}
	result.SchemaVersion = IdentitySecurityHTTPSchemaVersion
	writeJSON(w, http.StatusOK, result)
}

func identitySecurityOperation(parts []string) (string, bool) {
	if len(parts) != 2 {
		return "", false
	}
	operations := map[string]string{
		"password/enroll": "password_enroll", "password/change": "password_change",
		"password/recover": "password_recovery", "two-factor/enroll": "mfa_enroll",
		"two-factor/verify": "mfa_confirm",
	}
	op, ok := operations[parts[0]+"/"+parts[1]]
	return op, ok
}

func validateIdentitySecurityBody(body JSONMap) error {
	allowed := map[string]bool{"mutation_ticket_id": true, "step_up_receipt_id": true, "idempotency_key": true}
	for key := range body {
		normalized := strings.ToLower(strings.ReplaceAll(strings.ReplaceAll(key, "-", ""), "_", ""))
		if !allowed[key] || strings.Contains(normalized, "password") || strings.Contains(normalized, "secret") ||
			strings.Contains(normalized, "digest") || strings.Contains(normalized, "totp") || strings.Contains(normalized, "otp") ||
			strings.Contains(normalized, "recovery") || strings.Contains(normalized, "actor") || strings.Contains(normalized, "account") {
			return ErrIdentitySecurityUnavailable
		}
	}
	return nil
}
