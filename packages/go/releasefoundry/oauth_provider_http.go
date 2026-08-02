package releasefoundry

import (
	"errors"
	"net/http"
	"strings"
)

func (server *HTTPServer) handleOAuthProject(writer http.ResponseWriter, request *http.Request, projectID, providerName string, parts []string) {
	service := server.oauthProviders[providerName]
	if service == nil {
		writeError(writer, http.StatusNotFound, "not_found", "route not found")
		return
	}
	if len(parts) != 1 {
		writeError(writer, http.StatusNotFound, "not_found", "route not found")
		return
	}
	body, ok := readJSONBodyAllowGET(writer, request)
	if !ok {
		return
	}
	tenantID := firstNonEmpty(request.URL.Query().Get("tenant_id"), request.Header.Get("X-ReleaseFoundry-Tenant-ID"), stringValue(body, "tenant_id"))
	assertedAccountID := firstNonEmpty(request.URL.Query().Get("account_id"), stringValue(body, "account_id"))
	switch parts[0] {
	case "start":
		if request.Method != http.MethodGet && request.Method != http.MethodPost {
			writeError(writer, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
			return
		}
		result, err := service.Start(request.Context(), request, tenantID, projectID, assertedAccountID)
		if err != nil {
			writeOAuthError(writer, providerName, err)
			return
		}
		if request.Method == http.MethodGet && strings.EqualFold(request.URL.Query().Get("mode"), "redirect") {
			http.Redirect(writer, request, result.AuthorizationURL, http.StatusFound)
			return
		}
		writeJSON(writer, http.StatusOK, result)
	case "connection":
		if request.Method != http.MethodGet {
			writeError(writer, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
			return
		}
		result, err := service.Connection(request.Context(), request, tenantID, projectID, assertedAccountID)
		if err != nil {
			writeOAuthError(writer, providerName, err)
			return
		}
		writeJSON(writer, http.StatusOK, result)
	case "disconnect":
		if request.Method != http.MethodPost && request.Method != http.MethodDelete {
			writeError(writer, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
			return
		}
		result, err := service.Disconnect(request.Context(), request, tenantID, projectID, assertedAccountID)
		if err != nil {
			writeOAuthError(writer, providerName, err)
			return
		}
		writeJSON(writer, http.StatusOK, result)
	default:
		writeError(writer, http.StatusNotFound, "not_found", "route not found")
	}
}

func (server *HTTPServer) handleOAuthCallback(writer http.ResponseWriter, request *http.Request, providerName string) {
	service := server.oauthProviders[providerName]
	if service == nil {
		writeError(writer, http.StatusNotFound, "not_found", "route not found")
		return
	}
	if request.Method != http.MethodGet {
		writeError(writer, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
		return
	}
	if strings.TrimSpace(request.URL.Query().Get("error")) != "" {
		writeError(writer, http.StatusBadRequest, providerName+"_oauth_denied", providerName+" authorization was denied or cancelled")
		return
	}
	result, err := service.Callback(request.Context(), request, request.URL.Query().Get("code"), request.URL.Query().Get("state"))
	if err != nil {
		writeOAuthError(writer, providerName, err)
		return
	}
	writeJSON(writer, http.StatusOK, result)
}

func writeOAuthError(writer http.ResponseWriter, providerName string, err error) {
	var oauthError OAuthError
	if errors.As(err, &oauthError) {
		status := oauthError.Status
		if status == 0 {
			status = http.StatusInternalServerError
		}
		code := oauthError.Code
		if code == "" {
			code = providerName + "_oauth_failed"
		}
		message := oauthError.Message
		if message == "" {
			message = providerName + " OAuth request could not be completed"
		}
		writeError(writer, status, code, message)
		return
	}
	writeError(writer, http.StatusInternalServerError, providerName+"_oauth_failed", providerName+" OAuth request could not be completed")
}
