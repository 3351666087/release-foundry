package releasefoundry

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"time"
)

const (
	identityRequestBodyLimit = 32 * 1024
	identityReauthMaxAge     = 10 * time.Minute
)

type IdentityChallengeDelivery struct {
	ChallengeID    string
	Purpose        string
	Target         string
	Secret         string
	ExpiresAt      time.Time
	DeliveryMethod string
}

type IdentityChallengeDeliverer interface {
	DeliverIdentityChallenge(IdentityChallengeDelivery) error
}

type IdentityChallengeDelivererFunc func(IdentityChallengeDelivery) error

func (deliver IdentityChallengeDelivererFunc) DeliverIdentityChallenge(value IdentityChallengeDelivery) error {
	return deliver(value)
}

type IdentityRateLimiter interface {
	AllowIdentityAttempt(action, key string) bool
}

type IdentityAuditEvent struct {
	Action    string
	Outcome   string
	AccountID string
	Provider  string
	At        time.Time
}

type IdentityAuditSink interface {
	RecordIdentityAudit(IdentityAuditEvent)
}

type unavailableIdentityDeliverer struct{}

func (unavailableIdentityDeliverer) DeliverIdentityChallenge(IdentityChallengeDelivery) error {
	return &IdentityError{Code: IdentityUnavailable}
}

type allowIdentityRateLimiter struct{}

func (allowIdentityRateLimiter) AllowIdentityAttempt(string, string) bool { return true }

type discardIdentityAuditSink struct{}

func (discardIdentityAuditSink) RecordIdentityAudit(IdentityAuditEvent) {}

type identityEmailBeginRequest struct {
	Email  string `json:"email"`
	Locale string `json:"locale,omitempty"`
	Region string `json:"region,omitempty"`
}

type identityRegistrationCompleteRequest struct {
	ChallengeID string `json:"challenge_id"`
	Proof       string `json:"proof"`
	DisplayName string `json:"display_name,omitempty"`
}

type identityProofCompleteRequest struct {
	ChallengeID string `json:"challenge_id"`
	Proof       string `json:"proof"`
}

type identityCredentialBindRequest struct {
	BindingTicketID    string `json:"binding_ticket_id"`
	BindingTicketProof string `json:"binding_ticket_proof"`
	ExplicitConsent    bool   `json:"explicit_consent"`
}

type identityOAuthBeginRequest struct {
	Provider    string      `json:"provider"`
	Intent      OAuthIntent `json:"intent"`
	RedirectURI string      `json:"redirect_uri"`
}

type identityOAuthCompleteRequest struct {
	FlowID      string `json:"flow_id"`
	State       string `json:"state"`
	Code        string `json:"code"`
	DisplayName string `json:"display_name,omitempty"`
	Locale      string `json:"locale,omitempty"`
	Region      string `json:"region,omitempty"`
}

type identityAuthCompletion struct {
	SchemaVersion string    `json:"schema_version"`
	Status        string    `json:"status"`
	AccountID     string    `json:"account_id"`
	SessionID     string    `json:"session_id"`
	SessionToken  string    `json:"session_token"`
	ExpiresAt     time.Time `json:"expires_at"`
}

type identityOAuthLinkCompletion struct {
	SchemaVersion      string    `json:"schema_version"`
	Status             string    `json:"status"`
	Provider           string    `json:"provider"`
	BindingTicketID    string    `json:"binding_ticket_id"`
	BindingTicketProof string    `json:"binding_ticket_proof"`
	ExpiresAt          time.Time `json:"expires_at"`
}

func (server *HTTPServer) handleIdentityRoute(writer http.ResponseWriter, request *http.Request, parts []string) bool {
	if len(parts) == 2 && parts[0] == "v1" && parts[1] == "me" {
		server.handleIdentityMe(writer, request)
		return true
	}
	if len(parts) < 3 || parts[0] != "v1" || parts[1] != "identity" {
		return false
	}
	path := strings.Join(parts[2:], "/")
	switch path {
	case "registration/email/begin":
		server.handleIdentityRegistrationBegin(writer, request)
	case "registration/email/complete":
		server.handleIdentityRegistrationComplete(writer, request)
	case "login/email/begin":
		server.handleIdentityLoginBegin(writer, request)
	case "login/email/complete":
		server.handleIdentityLoginComplete(writer, request)
	case "oauth/begin":
		server.handleIdentityOAuthBegin(writer, request)
	case "oauth/complete":
		server.handleIdentityOAuthComplete(writer, request)
	case "mfa/complete":
		server.handleIdentityMFAComplete(writer, request)
	case "credentials/bind":
		server.handleIdentityCredentialBind(writer, request)
	case "sessions/revoke":
		server.handleIdentitySessionRevoke(writer, request)
	default:
		return false
	}
	return true
}

func (server *HTTPServer) handleIdentityOAuthBegin(writer http.ResponseWriter, request *http.Request) {
	if !requireIdentityMethod(writer, request, http.MethodPost) {
		return
	}
	var body identityOAuthBeginRequest
	if !decodeIdentityJSON(writer, request, &body) {
		return
	}
	if server.oauth == nil {
		writeOAuthServiceError(writer, &OAuthFlowError{Code: OAuthProviderUnavailable})
		return
	}

	provider := strings.ToLower(strings.TrimSpace(body.Provider))
	accountID := ""
	if body.Intent == OAuthIntentLink {
		var ok bool
		accountID, _, _, ok = server.authenticateIdentityRequest(request, true)
		if !ok {
			writeIdentityError(writer, http.StatusUnauthorized, "recent_reauthentication_required", "recent reauthentication required")
			return
		}
	}
	rateKey := provider + ":" + fingerprintIdentityValue(strings.TrimSpace(body.RedirectURI))
	if !server.identityRateLimiter.AllowIdentityAttempt("oauth.begin", rateKey) {
		writeIdentityError(writer, http.StatusTooManyRequests, "rate_limited", "try again later")
		return
	}
	result, err := server.oauth.Begin(request.Context(), provider, body.Intent, body.RedirectURI, accountID)
	if err != nil {
		server.recordIdentityAudit("oauth.begin", "failed", accountID, provider)
		writeOAuthServiceError(writer, err)
		return
	}
	server.recordIdentityAudit("oauth.begin", "accepted", accountID, result.Provider)
	writeIdentityOAuthBegin(writer, result)
}

func (server *HTTPServer) handleIdentityOAuthComplete(writer http.ResponseWriter, request *http.Request) {
	if !requireIdentityMethod(writer, request, http.MethodPost) {
		return
	}
	var body identityOAuthCompleteRequest
	if !decodeIdentityJSON(writer, request, &body) {
		return
	}
	if server.oauth == nil {
		writeOAuthServiceError(writer, &OAuthFlowError{Code: OAuthProviderUnavailable})
		return
	}
	if !server.identityRateLimiter.AllowIdentityAttempt("oauth.complete", fingerprintIdentityValue(body.FlowID)) {
		writeIdentityError(writer, http.StatusTooManyRequests, "rate_limited", "try again later")
		return
	}
	completed, err := server.oauth.Complete(request.Context(), body.FlowID, body.State, body.Code)
	if err != nil {
		server.recordIdentityAudit("oauth.complete", "failed", "", "")
		writeOAuthServiceError(writer, err)
		return
	}
	if completed.Intent != OAuthIntentRegistration &&
		(strings.TrimSpace(body.DisplayName) != "" ||
			strings.TrimSpace(body.Locale) != "" ||
			strings.TrimSpace(body.Region) != "") {
		server.recordIdentityAudit("oauth.complete", "failed", completed.AccountID, completed.Provider)
		writeOAuthServiceError(writer, &OAuthFlowError{Code: OAuthInvalidRequest})
		return
	}

	switch completed.Intent {
	case OAuthIntentRegistration:
		server.completeIdentityOAuthRegistration(writer, completed, body)
	case OAuthIntentLogin:
		server.completeIdentityOAuthLogin(writer, completed)
	case OAuthIntentLink:
		server.completeIdentityOAuthLink(writer, completed)
	default:
		server.recordIdentityAudit("oauth.complete", "failed", completed.AccountID, completed.Provider)
		writeOAuthServiceError(writer, &OAuthFlowError{Code: OAuthInvalidRequest})
	}
}

func (server *HTTPServer) completeIdentityOAuthRegistration(
	writer http.ResponseWriter,
	completed OAuthCompletionResult,
	body identityOAuthCompleteRequest,
) {
	account, err := server.identity.RegisterOAuthIdentity(
		completed.Identity,
		body.DisplayName,
		body.Locale,
		body.Region,
	)
	if err != nil {
		server.recordIdentityAudit("oauth.registration.complete", "failed", "", completed.Provider)
		writeIdentityServiceError(writer, err, false)
		return
	}
	view, err := server.identity.A3View(account.AccountID)
	if err != nil {
		writeIdentityServiceError(writer, err, false)
		return
	}
	server.recordIdentityAudit("oauth.registration.complete", "succeeded", account.AccountID, completed.Provider)
	writeJSON(writer, http.StatusCreated, JSONMap{
		"schema_version": IdentitySchemaVersion,
		"status":         "registered",
		"identity":       view,
	})
}

func (server *HTTPServer) completeIdentityOAuthLogin(writer http.ResponseWriter, completed OAuthCompletionResult) {
	result, err := server.identity.CompleteOAuthLogin(completed.Identity)
	if err != nil {
		server.recordIdentityAudit("oauth.login.complete", "failed", "", completed.Provider)
		writeIdentityServiceError(writer, err, true)
		return
	}
	if result.Status == "mfa_required" {
		challenge := IdentityChallenge{
			SchemaVersion:  IdentitySchemaVersion,
			ChallengeID:    result.MFAChallengeID,
			Purpose:        "mfa",
			DeliveryMethod: "email",
			ExpiresAt:      result.ExpiresAt,
			Secret:         result.MFASecret,
		}
		if result.MFADeliveryTarget == "" || server.deliverIdentityChallenge(challenge, result.MFADeliveryTarget) != nil {
			server.recordIdentityAudit("oauth.login.complete", "failed", result.AccountID, completed.Provider)
			writeIdentityServiceError(writer, &IdentityError{Code: IdentityUnavailable}, true)
			return
		}
		server.recordIdentityAudit("oauth.login.complete", "mfa_required", result.AccountID, completed.Provider)
		writeJSON(writer, http.StatusAccepted, JSONMap{
			"schema_version":   IdentitySchemaVersion,
			"status":           "mfa_required",
			"mfa_challenge_id": result.MFAChallengeID,
			"expires_at":       result.ExpiresAt,
		})
		return
	}
	server.recordIdentityAudit("oauth.login.complete", "succeeded", result.AccountID, completed.Provider)
	writeIdentityAuthCompletion(writer, result)
}

func (server *HTTPServer) completeIdentityOAuthLink(writer http.ResponseWriter, completed OAuthCompletionResult) {
	result, err := server.oauth.linkCompletionFromValidated(completed)
	if err != nil {
		server.recordIdentityAudit("oauth.link.complete", "failed", completed.AccountID, completed.Provider)
		writeIdentityServiceError(writer, err, false)
		return
	}
	server.recordIdentityAudit("oauth.link.complete", "ticket_issued", completed.AccountID, completed.Provider)
	writeIdentityOAuthLinkCompletion(writer, result)
}

func (server *HTTPServer) handleIdentityRegistrationBegin(writer http.ResponseWriter, request *http.Request) {
	if server.identityVerification != nil {
		server.handleIdentityBrowserEmailBegin(
			writer,
			request,
			IdentityVerificationRegistration,
		)
		return
	}
	if !requireIdentityMethod(writer, request, http.MethodPost) {
		return
	}
	var body identityEmailBeginRequest
	if !decodeIdentityJSON(writer, request, &body) {
		return
	}
	normalized, err := normalizeIdentityEmail(body.Email)
	if err != nil {
		writeIdentityServiceError(writer, err, false)
		return
	}
	if !server.identityRateLimiter.AllowIdentityAttempt("registration.email.begin", fingerprintIdentityValue(normalized)) {
		writeIdentityError(writer, http.StatusTooManyRequests, "rate_limited", "try again later")
		return
	}
	challenge, err := server.identity.BeginEmailRegistration(normalized, body.Locale, body.Region)
	if err == nil {
		err = server.deliverIdentityChallenge(challenge, normalized)
	}
	if err != nil {
		server.recordIdentityAudit("registration.email.begin", "failed", "", "")
		writeIdentityServiceError(writer, err, false)
		return
	}
	server.recordIdentityAudit("registration.email.begin", "accepted", "", "email_magic_link")
	writeJSON(writer, http.StatusAccepted, challenge)
}

func (server *HTTPServer) handleIdentityRegistrationComplete(writer http.ResponseWriter, request *http.Request) {
	if server.identityVerification != nil {
		server.handleIdentityBrowserEmailComplete(
			writer,
			request,
			IdentityVerificationRegistration,
		)
		return
	}
	if !requireIdentityMethod(writer, request, http.MethodPost) {
		return
	}
	var body identityRegistrationCompleteRequest
	if !decodeIdentityJSON(writer, request, &body) {
		return
	}
	if !server.identityRateLimiter.AllowIdentityAttempt("registration.email.complete", fingerprintIdentityValue(body.ChallengeID)) {
		writeIdentityError(writer, http.StatusTooManyRequests, "rate_limited", "try again later")
		return
	}
	account, err := server.identity.CompleteEmailRegistration(CompleteRegistrationRequest{
		ChallengeID: strings.TrimSpace(body.ChallengeID),
		Secret:      body.Proof,
		DisplayName: body.DisplayName,
	})
	if err != nil {
		server.recordIdentityAudit("registration.email.complete", "failed", "", "")
		writeIdentityServiceError(writer, err, false)
		return
	}
	view, err := server.identity.A3View(account.AccountID)
	if err != nil {
		writeIdentityServiceError(writer, err, false)
		return
	}
	server.recordIdentityAudit("registration.email.complete", "succeeded", account.AccountID, "email_magic_link")
	writeJSON(writer, http.StatusCreated, JSONMap{"schema_version": IdentitySchemaVersion, "status": "registered", "identity": view})
}

func (server *HTTPServer) handleIdentityLoginBegin(writer http.ResponseWriter, request *http.Request) {
	if server.identityVerification != nil {
		server.handleIdentityBrowserEmailBegin(
			writer,
			request,
			IdentityVerificationLogin,
		)
		return
	}
	if !requireIdentityMethod(writer, request, http.MethodPost) {
		return
	}
	var body identityEmailBeginRequest
	if !decodeIdentityJSON(writer, request, &body) {
		return
	}
	normalized, err := normalizeIdentityEmail(body.Email)
	if err != nil {
		writeIdentityServiceError(writer, err, true)
		return
	}
	if !server.identityRateLimiter.AllowIdentityAttempt("login.email.begin", fingerprintIdentityValue(normalized)) {
		writeIdentityError(writer, http.StatusTooManyRequests, "rate_limited", "try again later")
		return
	}
	challenge, err := server.identity.BeginEmailLogin(normalized)
	if err == nil {
		err = server.deliverIdentityChallenge(challenge, normalized)
	}
	if err != nil {
		server.recordIdentityAudit("login.email.begin", "failed", "", "")
		writeIdentityServiceError(writer, err, true)
		return
	}
	server.recordIdentityAudit("login.email.begin", "accepted", "", "email_magic_link")
	writeJSON(writer, http.StatusAccepted, challenge)
}

func (server *HTTPServer) handleIdentityLoginComplete(writer http.ResponseWriter, request *http.Request) {
	if server.identityVerification != nil {
		server.handleIdentityBrowserEmailComplete(
			writer,
			request,
			IdentityVerificationLogin,
		)
		return
	}
	if !requireIdentityMethod(writer, request, http.MethodPost) {
		return
	}
	var body identityProofCompleteRequest
	if !decodeIdentityJSON(writer, request, &body) {
		return
	}
	if !server.identityRateLimiter.AllowIdentityAttempt("login.email.complete", fingerprintIdentityValue(body.ChallengeID)) {
		writeIdentityError(writer, http.StatusTooManyRequests, "rate_limited", "try again later")
		return
	}
	result, err := server.identity.CompleteEmailLogin(strings.TrimSpace(body.ChallengeID), body.Proof)
	if err != nil {
		server.recordIdentityAudit("login.email.complete", "failed", "", "")
		writeIdentityServiceError(writer, err, true)
		return
	}
	if result.Status == "mfa_required" {
		challenge := IdentityChallenge{
			SchemaVersion:  IdentitySchemaVersion,
			ChallengeID:    result.MFAChallengeID,
			Purpose:        "mfa",
			DeliveryMethod: "email",
			ExpiresAt:      result.ExpiresAt,
			Secret:         result.MFASecret,
		}
		if result.MFADeliveryTarget == "" || server.deliverIdentityChallenge(challenge, result.MFADeliveryTarget) != nil {
			writeIdentityServiceError(writer, &IdentityError{Code: IdentityUnavailable}, true)
			return
		}
		server.recordIdentityAudit("login.email.complete", "mfa_required", result.AccountID, "email_magic_link")
		writeJSON(writer, http.StatusAccepted, JSONMap{
			"schema_version":   IdentitySchemaVersion,
			"status":           "mfa_required",
			"mfa_challenge_id": result.MFAChallengeID,
			"expires_at":       result.ExpiresAt,
		})
		return
	}
	server.recordIdentityAudit("login.email.complete", "succeeded", result.AccountID, "email_magic_link")
	writeIdentityAuthCompletion(writer, result)
}

func (server *HTTPServer) handleIdentityMFAComplete(writer http.ResponseWriter, request *http.Request) {
	if !requireIdentityMethod(writer, request, http.MethodPost) {
		return
	}
	var body identityProofCompleteRequest
	if !decodeIdentityJSON(writer, request, &body) {
		return
	}
	if !server.identityRateLimiter.AllowIdentityAttempt("mfa.complete", fingerprintIdentityValue(body.ChallengeID)) {
		writeIdentityError(writer, http.StatusTooManyRequests, "rate_limited", "try again later")
		return
	}
	result, err := server.identity.CompleteMFA(strings.TrimSpace(body.ChallengeID), body.Proof)
	if err != nil {
		server.recordIdentityAudit("mfa.complete", "failed", "", "")
		writeIdentityServiceError(writer, err, true)
		return
	}
	server.recordIdentityAudit("mfa.complete", "succeeded", result.AccountID, "")
	writeIdentityAuthCompletion(writer, result)
}

func (server *HTTPServer) handleIdentityMe(writer http.ResponseWriter, request *http.Request) {
	if !requireIdentityMethod(writer, request, http.MethodGet) {
		return
	}
	if server.identitySessions != nil && server.unifiedIdentityHTTPStore() != nil {
		session, ok := server.resolveTrustedIdentityHTTPSession(writer, request)
		if !ok {
			return
		}
		account, err := server.unifiedIdentityHTTPStore().GetIdentityAccount(
			request.Context(), session.AccountID,
		)
		if err != nil {
			writeIdentityHTTPError(writer, err)
			return
		}
		writeJSON(writer, http.StatusOK, publicIdentityAccount(account))
		return
	}
	accountID, _, _, ok := server.authenticateIdentityRequest(request, false)
	if !ok {
		writeIdentityError(writer, http.StatusUnauthorized, "authentication_required", "authentication required")
		return
	}
	view, err := server.identity.A3View(accountID)
	if err != nil {
		writeIdentityServiceError(writer, err, false)
		return
	}
	writeJSON(writer, http.StatusOK, view)
}

func (server *HTTPServer) handleIdentityCredentialBind(writer http.ResponseWriter, request *http.Request) {
	if !requireIdentityMethod(writer, request, http.MethodPost) {
		return
	}
	accountID, _, _, ok := server.authenticateIdentityRequest(request, true)
	if !ok {
		writeIdentityError(writer, http.StatusUnauthorized, "recent_reauthentication_required", "recent reauthentication required")
		return
	}
	var body identityCredentialBindRequest
	if !decodeIdentityJSON(writer, request, &body) {
		return
	}
	credential, err := server.identity.BindCredentialWithTicket(
		accountID,
		accountID,
		body.BindingTicketID,
		body.BindingTicketProof,
		body.ExplicitConsent,
		true,
	)
	if err != nil {
		server.recordIdentityAudit("credential.bind", "failed", accountID, "")
		writeIdentityServiceError(writer, err, false)
		return
	}
	server.recordIdentityAudit("credential.bind", "succeeded", accountID, credential.Provider)
	view, err := server.identity.A3View(accountID)
	if err != nil {
		writeIdentityServiceError(writer, err, false)
		return
	}
	writeJSON(writer, http.StatusOK, JSONMap{"schema_version": IdentitySchemaVersion, "status": "bound", "identity": view})
}

func (server *HTTPServer) handleIdentitySessionRevoke(writer http.ResponseWriter, request *http.Request) {
	if !requireIdentityMethod(writer, request, http.MethodPost) {
		return
	}
	if identitySessionCookiePresent(request, IdentitySessionCookieName) {
		if validateIdentitySessionRefreshBrowserRequest(request) != nil {
			writeIdentityError(writer, http.StatusForbidden, "identity_session_origin_rejected", "identity session origin was rejected")
			return
		}
		session, ok := server.resolveTrustedIdentityHTTPSession(writer, request)
		if !ok {
			clearIdentitySessionCookies(writer)
			return
		}
		revoker, ok := server.identitySessions.(IdentityHTTPSessionRevoker)
		if !ok || revoker.RevokeIdentityHTTPSession(request.Context(), request) != nil {
			writeIdentityError(writer, http.StatusServiceUnavailable, "identity_session_revoke_unavailable", "identity session could not be revoked")
			return
		}
		clearIdentitySessionCookies(writer)
		server.recordIdentityAudit("session.revoke", "succeeded", session.AccountID, "")
		writeJSON(writer, http.StatusOK, JSONMap{"schema_version": IdentitySchemaVersion, "status": "revoked"})
		return
	}
	accountID, sessionID, _, ok := server.authenticateIdentityRequest(request, false)
	if !ok {
		writeIdentityError(writer, http.StatusUnauthorized, "authentication_required", "authentication required")
		return
	}
	server.identity.RevokeSession(sessionID)
	server.recordIdentityAudit("session.revoke", "succeeded", accountID, "")
	writeJSON(writer, http.StatusOK, JSONMap{"schema_version": IdentitySchemaVersion, "status": "revoked"})
}

func (server *HTTPServer) deliverIdentityChallenge(challenge IdentityChallenge, target string) error {
	return server.identityDelivery.DeliverIdentityChallenge(IdentityChallengeDelivery{
		ChallengeID:    challenge.ChallengeID,
		Purpose:        challenge.Purpose,
		Target:         target,
		Secret:         challenge.Secret,
		ExpiresAt:      challenge.ExpiresAt,
		DeliveryMethod: challenge.DeliveryMethod,
	})
}

func (server *HTTPServer) authenticateIdentityRequest(request *http.Request, fresh bool) (string, string, string, bool) {
	sessionID := strings.TrimSpace(request.Header.Get("X-ReleaseFoundry-Session-ID"))
	authorization := strings.TrimSpace(request.Header.Get("Authorization"))
	if sessionID == "" || !strings.HasPrefix(authorization, "Bearer ") {
		return "", "", "", false
	}
	token := strings.TrimSpace(strings.TrimPrefix(authorization, "Bearer "))
	if token == "" {
		return "", "", "", false
	}
	if fresh {
		accountID, ok := server.identity.VerifyFreshSession(sessionID, token, identityReauthMaxAge)
		return accountID, sessionID, token, ok
	}
	accountID, ok := server.identity.VerifySession(sessionID, token)
	return accountID, sessionID, token, ok
}

func (server *HTTPServer) recordIdentityAudit(action, outcome, accountID, provider string) {
	server.identityAudit.RecordIdentityAudit(IdentityAuditEvent{
		Action:    action,
		Outcome:   outcome,
		AccountID: accountID,
		Provider:  provider,
		At:        server.identity.now().UTC(),
	})
}

func requireIdentityMethod(writer http.ResponseWriter, request *http.Request, method string) bool {
	if request.Method == method {
		return true
	}
	writer.Header().Set("Allow", method)
	writeIdentityError(writer, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
	return false
}

func decodeIdentityJSON(writer http.ResponseWriter, request *http.Request, target any) bool {
	if request.Body == nil || request.Body == http.NoBody {
		writeIdentityError(writer, http.StatusBadRequest, "invalid_json", "request body must be a JSON object")
		return false
	}
	defer request.Body.Close()
	limited := http.MaxBytesReader(writer, request.Body, identityRequestBodyLimit)
	decoder := json.NewDecoder(limited)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		writeIdentityError(writer, http.StatusBadRequest, "invalid_json", "request body must be a valid JSON object")
		return false
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		writeIdentityError(writer, http.StatusBadRequest, "invalid_json", "request body must contain exactly one JSON object")
		return false
	}
	return true
}

func writeIdentityAuthCompletion(writer http.ResponseWriter, result LoginResult) {
	writer.Header().Set("Cache-Control", "no-store")
	writer.Header().Set("Pragma", "no-cache")
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(writer).Encode(identityAuthCompletion{
		SchemaVersion: IdentitySchemaVersion,
		Status:        "authenticated",
		AccountID:     result.AccountID,
		SessionID:     result.SessionID,
		SessionToken:  result.SessionToken,
		ExpiresAt:     result.ExpiresAt,
	})
}

func writeIdentityOAuthBegin(writer http.ResponseWriter, result OAuthBeginResult) {
	writer.Header().Set("Cache-Control", "no-store")
	writer.Header().Set("Pragma", "no-cache")
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(http.StatusAccepted)
	_ = json.NewEncoder(writer).Encode(result)
}

func writeIdentityOAuthLinkCompletion(writer http.ResponseWriter, result OAuthLinkCompletion) {
	writer.Header().Set("Cache-Control", "no-store")
	writer.Header().Set("Pragma", "no-cache")
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(writer).Encode(identityOAuthLinkCompletion{
		SchemaVersion:      IdentitySchemaVersion,
		Status:             result.Status,
		Provider:           result.Provider,
		BindingTicketID:    result.BindingTicket.TicketID,
		BindingTicketProof: result.BindingTicket.Secret,
		ExpiresAt:          result.BindingTicket.ExpiresAt,
	})
}

func writeOAuthServiceError(writer http.ResponseWriter, err error) {
	var oauthErr *OAuthFlowError
	if !errors.As(err, &oauthErr) {
		writeIdentityError(writer, http.StatusServiceUnavailable, string(OAuthProviderUnavailable), "OAuth service unavailable")
		return
	}
	switch oauthErr.Code {
	case OAuthInvalidRequest:
		writeIdentityError(writer, http.StatusBadRequest, string(oauthErr.Code), "invalid OAuth request")
	case OAuthRedirectNotAllowed:
		writeIdentityError(writer, http.StatusBadRequest, string(oauthErr.Code), "OAuth redirect URI is not allowed")
	case OAuthInvalidOrExpiredFlow:
		writeIdentityError(writer, http.StatusUnauthorized, string(oauthErr.Code), "invalid or expired OAuth flow")
	case OAuthProviderUnavailable, OAuthExchangeFailed:
		writeIdentityError(writer, http.StatusServiceUnavailable, string(oauthErr.Code), "OAuth provider unavailable")
	default:
		writeIdentityError(writer, http.StatusBadRequest, string(oauthErr.Code), "OAuth request failed")
	}
}

func writeIdentityServiceError(writer http.ResponseWriter, err error, genericLogin bool) {
	var identityErr *IdentityError
	if !errors.As(err, &identityErr) {
		writeIdentityError(writer, http.StatusServiceUnavailable, "identity_service_unavailable", "identity service unavailable")
		return
	}
	if genericLogin && identityErr.Code != IdentityUnavailable {
		writeIdentityError(writer, http.StatusUnauthorized, "invalid_credentials", "invalid credentials")
		return
	}
	switch identityErr.Code {
	case IdentityInvalidInput:
		writeIdentityError(writer, http.StatusBadRequest, string(identityErr.Code), "invalid identity request")
	case IdentityInvalidProof:
		writeIdentityError(writer, http.StatusUnauthorized, string(identityErr.Code), "invalid or expired proof")
	case IdentityRegistrationConflict, IdentityBindingConflict:
		writeIdentityError(writer, http.StatusConflict, string(identityErr.Code), "identity conflict")
	case IdentityConsentRequired, IdentityReauthRequired:
		writeIdentityError(writer, http.StatusForbidden, string(identityErr.Code), "additional authorization required")
	case IdentityNotFound:
		writeIdentityError(writer, http.StatusNotFound, string(identityErr.Code), "identity not found")
	case IdentityUnavailable:
		writeIdentityError(writer, http.StatusServiceUnavailable, string(identityErr.Code), "identity service unavailable")
	default:
		writeIdentityError(writer, http.StatusBadRequest, string(identityErr.Code), "identity request failed")
	}
}

func writeIdentityError(writer http.ResponseWriter, status int, code, message string) {
	writeJSON(writer, status, JSONMap{
		"schema_version": IdentitySchemaVersion,
		"status":         "error",
		"error":          JSONMap{"code": code, "message": message},
	})
}
