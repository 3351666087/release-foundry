package ashrclone

import (
	"net/http"
	"net/url"
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
	if _, err := oauthFirstLoginStartOrigin(request); err != nil {
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

// oauthFirstLoginStartOrigin preserves the strict Origin contract for
// script/fetch requests while also accepting a standard browser top-level
// same-origin navigation, which commonly omits Origin on GET navigations.
func oauthFirstLoginStartOrigin(request *http.Request) (string, error) {
	if request == nil || request.Host == "" ||
		request.Host != strings.TrimSpace(request.Host) {
		return "", errIdentityBrowserIntentInvalid
	}
	for _, header := range []string{
		"Forwarded",
		"X-Forwarded-For",
		"X-Forwarded-Host",
		"X-Real-IP",
	} {
		for _, value := range request.Header.Values(header) {
			if strings.TrimSpace(value) != "" {
				return "", errIdentityBrowserIntentInvalid
			}
		}
	}
	if len(request.Header.Values("Origin")) > 0 {
		return identityBrowserVerificationOrigin(request)
	}

	if !singleOAuthFetchMetadataValue(request, "Sec-Fetch-Site", "same-origin") ||
		!singleOAuthFetchMetadataValue(request, "Sec-Fetch-Mode", "navigate") ||
		!singleOAuthFetchMetadataValue(request, "Sec-Fetch-Dest", "document") {
		return "", errIdentityBrowserIntentInvalid
	}
	referers := request.Header.Values("Referer")
	if len(referers) != 1 ||
		referers[0] == "" ||
		referers[0] != strings.TrimSpace(referers[0]) {
		return "", errIdentityBrowserIntentInvalid
	}
	referer, err := url.Parse(referers[0])
	if err != nil ||
		!strings.EqualFold(referer.Scheme, "https") ||
		referer.Host == "" ||
		!strings.EqualFold(referer.Host, request.Host) ||
		referer.User != nil ||
		referer.Fragment != "" {
		return "", errIdentityBrowserIntentInvalid
	}
	return "https://" + strings.ToLower(request.Host), nil
}

func singleOAuthFetchMetadataValue(
	request *http.Request,
	header string,
	expected string,
) bool {
	if request == nil {
		return false
	}
	values := request.Header.Values(header)
	return len(values) == 1 &&
		values[0] != "" &&
		values[0] == strings.TrimSpace(values[0]) &&
		strings.EqualFold(values[0], expected)
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
	code, state, ok := strictOAuthFirstLoginCallbackQuery(request, providerName)
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

const maxOAuthFirstLoginCallbackRawQueryLength = 16 * 1024

func strictOAuthFirstLoginCallbackQuery(
	request *http.Request,
	providerName string,
) (string, string, bool) {
	if request == nil ||
		request.URL == nil ||
		request.URL.RawQuery == "" ||
		len(request.URL.RawQuery) > maxOAuthFirstLoginCallbackRawQueryLength {
		return "", "", false
	}
	query, err := url.ParseQuery(request.URL.RawQuery)
	if err != nil {
		return "", "", false
	}
	for key, values := range query {
		if len(values) != 1 ||
			!validOAuthFirstLoginCallbackParameter(
				providerName,
				key,
				values[0],
			) {
			return "", "", false
		}
	}
	code, codeExists := query["code"]
	state, stateExists := query["state"]
	if !codeExists || !stateExists ||
		len(code) != 1 || len(state) != 1 {
		return "", "", false
	}
	return code[0], state[0], true
}

func validOAuthFirstLoginCallbackParameter(
	providerName string,
	key string,
	value string,
) bool {
	if value == "" ||
		value != strings.TrimSpace(value) ||
		strings.ContainsAny(value, "\x00\r\n\t") {
		return false
	}
	switch key {
	case "code":
		return len(value) <= 4096
	case "state":
		return len(value) <= 1024
	}
	if providerName != "google" {
		return false
	}
	switch key {
	case "iss":
		return value == "https://accounts.google.com"
	case "scope":
		return len(value) <= 8192
	case "authuser":
		if len(value) > 16 {
			return false
		}
		for _, character := range value {
			if character < '0' || character > '9' {
				return false
			}
		}
		return true
	case "prompt":
		switch value {
		case "none", "consent", "select_account", "login":
			return true
		default:
			return false
		}
	default:
		return false
	}
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
