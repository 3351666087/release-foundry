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
	if operation, action, ok := identitySecurityServiceOperation(parts); ok {
		server.handleIdentitySecurityService(
			w,
			r,
			session,
			operation,
			action,
		)
		return
	}
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

func (server *HTTPServer) handleIdentitySecurityService(
	writer http.ResponseWriter,
	request *http.Request,
	session IdentityHTTPSession,
	operation string,
	action string,
) {
	if request.Method != http.MethodPost {
		writeError(
			writer,
			http.StatusMethodNotAllowed,
			"method_not_allowed",
			"method not allowed",
		)
		return
	}
	if server.identitySecurityService == nil {
		writeError(
			writer,
			http.StatusServiceUnavailable,
			"identity_security_unavailable",
			"identity security capability is unavailable",
		)
		return
	}
	if _, err := identityBrowserVerificationOrigin(request); err != nil {
		writeError(
			writer,
			http.StatusForbidden,
			"identity_security_origin_rejected",
			"identity security request origin could not be verified",
		)
		return
	}
	body, ok := readJSONBody(writer, request)
	if !ok {
		return
	}
	if err := validateIdentitySecurityServiceBody(
		body,
		operation,
		action,
	); err != nil {
		writeError(
			writer,
			http.StatusBadRequest,
			"invalid_identity_security_request",
			"identity security request is invalid",
		)
		return
	}
	headerKey := strings.TrimSpace(request.Header.Get("Idempotency-Key"))
	bodyKey := strings.TrimSpace(stringValue(body, "idempotency_key"))
	if headerKey == "" || bodyKey == "" || headerKey != bodyKey ||
		!validIdentitySecurityIdempotencyKey(headerKey) {
		writeError(
			writer,
			http.StatusBadRequest,
			"invalid_identity_security_request",
			"a matching idempotency key is required",
		)
		return
	}
	if action == "begin" {
		password := stringValue(body, "password")
		delete(body, "password")
		result, err := server.identitySecurityService.Begin(
			request.Context(),
			session,
			IdentitySecurityBeginRequest{
				Operation:      operation,
				IdempotencyKey: headerKey,
				Password:       password,
			},
		)
		password = ""
		writeIdentitySecurityServiceResult(writer, result, err)
		return
	}
	if action == "confirm" {
		challengeID := stringValue(body, "challenge_id")
		code := stringValue(body, "code")
		delete(body, "code")
		result, err := server.identitySecurityService.Confirm(
			request.Context(),
			session,
			IdentitySecurityConfirmRequest{
				IdempotencyKey: headerKey,
				ChallengeID:    challengeID,
				Code:           code,
			},
		)
		code = ""
		writeIdentitySecurityServiceResult(writer, result, err)
		return
	}
	recoveryCode := stringValue(body, "recovery_code")
	delete(body, "recovery_code")
	result, err := server.identitySecurityService.MutateTwoFactor(
		request.Context(),
		session,
		IdentitySecurityTwoFactorMutationRequest{
			Operation:      operation,
			IdempotencyKey: headerKey,
			RecoveryCode:   recoveryCode,
		},
	)
	recoveryCode = ""
	if operation == "mfa_recovery_rotate" {
		writer.Header().Set("Cache-Control", "no-store")
		writer.Header().Set("Pragma", "no-cache")
	}
	writeIdentitySecurityServiceResult(writer, result, err)
}

func identitySecurityServiceOperation(
	parts []string,
) (string, string, bool) {
	key := strings.Join(parts, "/")
	routes := map[string]struct {
		operation string
		action    string
	}{
		"password/enroll/begin": {
			operation: "password_enroll",
			action:    "begin",
		},
		"password/change/begin": {
			operation: "password_change",
			action:    "begin",
		},
		"password/recover/begin": {
			operation: "password_recovery",
			action:    "begin",
		},
		"two-factor/enroll/begin": {
			operation: "mfa_enroll",
			action:    "begin",
		},
		"two-factor/enroll/confirm": {
			operation: "mfa_confirm",
			action:    "confirm",
		},
		"two-factor/disable": {
			operation: "mfa_disable",
			action:    "mutation",
		},
		"two-factor/recovery-codes/consume": {
			operation: "mfa_recovery_consume",
			action:    "mutation",
		},
		"two-factor/recovery-codes/rotate": {
			operation: "mfa_recovery_rotate",
			action:    "mutation",
		},
	}
	route, ok := routes[key]
	return route.operation, route.action, ok
}

func validateIdentitySecurityServiceBody(
	body JSONMap,
	operation string,
	action string,
) error {
	if body == nil {
		return ErrIdentitySecurityRejected
	}
	allowed := map[string]bool{"idempotency_key": true}
	switch {
	case action == "begin" && operation == "mfa_enroll":
	case action == "begin":
		allowed["password"] = true
	case action == "confirm" && operation == "mfa_confirm":
		allowed["challenge_id"] = true
		allowed["code"] = true
	case action == "mutation" && operation == "mfa_recovery_consume":
		allowed["recovery_code"] = true
	case action == "mutation" &&
		(operation == "mfa_recovery_rotate" || operation == "mfa_disable"):
	default:
		return ErrIdentitySecurityRejected
	}
	for key := range body {
		if !allowed[key] {
			return ErrIdentitySecurityRejected
		}
	}
	if _, ok := body["idempotency_key"].(string); !ok {
		return ErrIdentitySecurityRejected
	}
	if action == "begin" && operation != "mfa_enroll" {
		if _, ok := body["password"].(string); !ok {
			return ErrIdentitySecurityRejected
		}
	}
	if action == "confirm" {
		if _, ok := body["challenge_id"].(string); !ok {
			return ErrIdentitySecurityRejected
		}
		if _, ok := body["code"].(string); !ok {
			return ErrIdentitySecurityRejected
		}
	}
	if action == "mutation" && operation == "mfa_recovery_consume" {
		if _, ok := body["recovery_code"].(string); !ok {
			return ErrIdentitySecurityRejected
		}
	}
	return nil
}

func writeIdentitySecurityServiceResult[T any](
	writer http.ResponseWriter,
	result T,
	err error,
) {
	if err == nil {
		writeJSON(writer, http.StatusOK, result)
		return
	}
	if errors.Is(err, ErrIdentitySecurityRejected) {
		writeError(
			writer,
			http.StatusForbidden,
			"identity_security_request_rejected",
			"identity security request could not be completed",
		)
		return
	}
	writeError(
		writer,
		http.StatusServiceUnavailable,
		"identity_security_unavailable",
		"identity security capability is unavailable",
	)
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
