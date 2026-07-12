package ashrclone

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"time"
)

const IdentitySecurityHTTPSchemaVersion = "ashr.identity_security_http.v1"

var ErrIdentitySecurityUnavailable = errors.New("identity security mutation unavailable")

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
	ResolveIdentitySecurityMutationTicket(context.Context, string, string, string) (IdentitySecurityMutationTicket, error)
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
	GetIdentitySecurityPosture(context.Context, string) (JSONMap, error)
	MutateIdentitySecurity(context.Context, IdentitySecurityMutation) (JSONMap, error)
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
		writeIdentitySecurityResult(w, posture, err)
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
	if headerKey == "" || bodyKey == "" || headerKey != bodyKey || ticketID == "" || stepUpID == "" {
		writeError(w, http.StatusBadRequest, "invalid_security_mutation", "mutation ticket, step-up receipt, and matching idempotency key are required")
		return
	}
	ticket, err := server.identitySecurityTickets.ResolveIdentitySecurityMutationTicket(r.Context(), ticketID, stepUpID, operation)
	if err != nil || ticket.AccountID != session.AccountID || ticket.Operation != operation || !ticket.ExpiresAt.After(time.Now().UTC()) {
		writeError(w, http.StatusForbidden, "identity_security_mutation_rejected", "identity security mutation could not be authorized")
		return
	}
	result, err := server.identitySecurity.MutateIdentitySecurity(r.Context(), IdentitySecurityMutation{
		AccountID: session.AccountID, ActorID: session.ActorID, SessionID: session.SessionID,
		Operation: operation, IdempotencyKey: headerKey, Ticket: ticket,
	})
	writeIdentitySecurityResult(w, result, err)
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

func writeIdentitySecurityResult(w http.ResponseWriter, result JSONMap, err error) {
	if err != nil {
		writeError(w, http.StatusForbidden, "identity_security_mutation_rejected", "identity security mutation could not be completed")
		return
	}
	result["schema_version"] = IdentitySecurityHTTPSchemaVersion
	writeJSON(w, http.StatusOK, result)
}
