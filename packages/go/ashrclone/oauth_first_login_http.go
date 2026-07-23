package ashrclone

import (
	"net/http"
	"strings"
)

type oauthFirstLoginIntentHeaderWriter struct {
	header http.Header
}

func (writer *oauthFirstLoginIntentHeaderWriter) Header() http.Header {
	return writer.header
}

func (*oauthFirstLoginIntentHeaderWriter) Write([]byte) (int, error) {
	return 0, nil
}

func (*oauthFirstLoginIntentHeaderWriter) WriteHeader(int) {}

func (server *HTTPServer) handleOAuthFirstLogin(
	writer http.ResponseWriter,
	request *http.Request,
	providerName string,
	action string,
) {
	setOAuthFirstLoginResponseHeaders(writer)
	service := server.oauthFirstLogins[providerName]
	if service == nil || server.oauthFirstLoginIntents == nil {
		writeError(writer, http.StatusNotFound, "not_found", "route not found")
		return
	}
	if request.Method != http.MethodGet {
		writeError(writer, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
		return
	}
	if err := server.oauthFirstLoginIntents.ValidateOAuthFirstLoginRequest(request); err != nil {
		writeError(writer, http.StatusUpgradeRequired, "oauth_first_login_secure_transport_required", "OAuth first login requires HTTPS")
		return
	}
	if !service.MatchesCallbackHost(request.Host) {
		writeError(writer, http.StatusForbidden, "oauth_first_login_host_rejected", "OAuth first-login host was rejected")
		return
	}
	switch action {
	case "start":
		server.handleOAuthFirstLoginStart(writer, request, service, providerName)
	case "callback":
		server.handleOAuthFirstLoginCallback(writer, request, service, providerName)
	default:
		writeError(writer, http.StatusNotFound, "not_found", "route not found")
	}
}

func (server *HTTPServer) handleOAuthFirstLoginStart(
	writer http.ResponseWriter,
	request *http.Request,
	service *OAuthFirstLoginService,
	providerName string,
) {
	if request.URL.RawQuery != "" {
		writeError(writer, http.StatusBadRequest, "oauth_first_login_request_invalid", "OAuth first-login start request is invalid")
		return
	}
	if _, err := identityBrowserVerificationOrigin(request); err != nil {
		writeError(writer, http.StatusForbidden, "oauth_first_login_origin_rejected", "OAuth first-login origin was rejected")
		return
	}
	prepared, err := service.prepareStart(request.Context())
	if err != nil {
		writeOAuthError(writer, providerName, err)
		return
	}
	transaction := prepared.Transaction
	intentWriter := &oauthFirstLoginIntentHeaderWriter{header: make(http.Header)}
	if err := server.oauthFirstLoginIntents.IssueOAuthFirstLoginIntent(
		intentWriter,
		request,
		OAuthFirstLoginIntentIssue{
			IntentID:       transaction.IntentID,
			Provider:       transaction.Provider,
			Purpose:        transaction.Purpose,
			OrganizationID: transaction.OrganizationID,
			ProjectID:      transaction.ProjectID,
			StateHash:      transaction.StateHash,
			ExpiresAt:      transaction.ExpiresAt,
		},
	); err != nil {
		writeError(writer, http.StatusForbidden, "oauth_first_login_intent_rejected", "OAuth browser intent was rejected")
		return
	}
	if err := service.commitStart(request.Context(), transaction); err != nil {
		writeOAuthError(writer, providerName, err)
		return
	}
	for _, value := range intentWriter.header.Values("Set-Cookie") {
		writer.Header().Add("Set-Cookie", value)
	}
	writeEmptyOAuthFirstLoginRedirect(writer, http.StatusFound, prepared.AuthorizationURL)
}

func (server *HTTPServer) handleOAuthFirstLoginCallback(
	writer http.ResponseWriter,
	request *http.Request,
	service *OAuthFirstLoginService,
	providerName string,
) {
	if server.identitySessionReceiptTransport == nil {
		writeError(writer, http.StatusServiceUnavailable, "identity_session_transport_unavailable", "identity session handoff is not configured")
		return
	}
	if err := server.identitySessionReceiptTransport.ValidateIdentitySessionRequest(request); err != nil {
		writeError(writer, http.StatusUpgradeRequired, "identity_session_secure_transport_required", "identity session handoff requires HTTPS")
		return
	}
	code, state, ok := strictOAuthFirstLoginCallbackQuery(request)
	if !ok {
		writeError(writer, http.StatusBadRequest, "invalid_oauth_callback", "OAuth callback is invalid")
		return
	}
	result, receipt, err := service.complete(
		request.Context(),
		code,
		state,
		func(transaction OAuthFirstLoginTransaction) error {
			return server.oauthFirstLoginIntents.ValidateOAuthFirstLoginIntent(
				request,
				OAuthFirstLoginIntentValidation{
					IntentID:       transaction.IntentID,
					Provider:       transaction.Provider,
					Purpose:        transaction.Purpose,
					OrganizationID: transaction.OrganizationID,
					ProjectID:      transaction.ProjectID,
					StateHash:      transaction.StateHash,
				},
			)
		},
	)
	if err != nil {
		writeOAuthError(writer, providerName, err)
		return
	}
	if result.SessionID == "" {
		writeError(writer, http.StatusInternalServerError, "oauth_first_login_session_invalid", "OAuth first login could not be completed")
		return
	}
	if err := server.identitySessionReceiptTransport.WriteIdentitySessionReceipt(
		writer,
		request,
		receipt,
	); err != nil {
		writeError(writer, http.StatusInternalServerError, "identity_session_handoff_failed", "identity session handoff failed")
		return
	}
	server.oauthFirstLoginIntents.ClearOAuthFirstLoginIntent(writer)
	writeEmptyOAuthFirstLoginRedirect(writer, http.StatusSeeOther, "/console")
}

func strictOAuthFirstLoginCallbackQuery(request *http.Request) (string, string, bool) {
	if request == nil || request.URL == nil || request.URL.RawQuery == "" {
		return "", "", false
	}
	query := request.URL.Query()
	if len(query) != 2 {
		return "", "", false
	}
	for _, key := range []string{"code", "state"} {
		values, exists := query[key]
		if !exists || len(values) != 1 || values[0] == "" ||
			values[0] != strings.TrimSpace(values[0]) ||
			strings.ContainsAny(values[0], "\x00\r\n\t") {
			return "", "", false
		}
	}
	return query.Get("code"), query.Get("state"), true
}

func setOAuthFirstLoginResponseHeaders(writer http.ResponseWriter) {
	writer.Header().Set("Cache-Control", "no-store")
	writer.Header().Set("Pragma", "no-cache")
	writer.Header().Set("X-Content-Type-Options", "nosniff")
}

func writeEmptyOAuthFirstLoginRedirect(
	writer http.ResponseWriter,
	status int,
	location string,
) {
	writer.Header().Del("Content-Type")
	writer.Header().Set("Location", location)
	writer.WriteHeader(status)
}
