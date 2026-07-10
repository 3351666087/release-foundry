package ashrclone

import (
	"errors"
	"net/http"
	"strings"
)

func (server *HTTPServer) handleGitHubOAuthProject(writer http.ResponseWriter, request *http.Request, projectID string, parts []string) {
	if server.githubOAuth == nil {
		writeError(writer, http.StatusServiceUnavailable, "github_oauth_unavailable", "GitHub OAuth is not configured")
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
	tenantID := firstNonEmpty(request.URL.Query().Get("tenant_id"), request.Header.Get("X-Ashr-Tenant-ID"), stringValue(body, "tenant_id"))
	accountID := firstNonEmpty(request.URL.Query().Get("account_id"), stringValue(body, "account_id"))
	switch parts[0] {
	case "start":
		if request.Method != http.MethodGet && request.Method != http.MethodPost {
			writeError(writer, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
			return
		}
		result, err := server.githubOAuth.Start(request.Context(), request, tenantID, projectID, accountID)
		if err != nil {
			writeGitHubOAuthError(writer, err)
			return
		}
		if request.Method == http.MethodGet && strings.EqualFold(request.URL.Query().Get("mode"), "redirect") {
			http.Redirect(writer, request, result.AuthorizationURL, http.StatusFound)
			return
		}
		writeJSON(writer, http.StatusOK, result)
	case "disconnect":
		if request.Method != http.MethodPost && request.Method != http.MethodDelete {
			writeError(writer, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
			return
		}
		result, err := server.githubOAuth.Disconnect(request.Context(), request, tenantID, projectID, accountID)
		if err != nil {
			writeGitHubOAuthError(writer, err)
			return
		}
		writeJSON(writer, http.StatusOK, result)
	default:
		writeError(writer, http.StatusNotFound, "not_found", "route not found")
	}
}

func (server *HTTPServer) handleGitHubOAuthCallback(writer http.ResponseWriter, request *http.Request) {
	if server.githubOAuth == nil {
		writeError(writer, http.StatusServiceUnavailable, "github_oauth_unavailable", "GitHub OAuth is not configured")
		return
	}
	if request.Method != http.MethodGet {
		writeError(writer, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
		return
	}
	if strings.TrimSpace(request.URL.Query().Get("error")) != "" {
		writeError(writer, http.StatusBadRequest, "github_oauth_denied", "GitHub authorization was denied or cancelled")
		return
	}
	result, err := server.githubOAuth.Callback(request.Context(), request, request.URL.Query().Get("code"), request.URL.Query().Get("state"))
	if err != nil {
		writeGitHubOAuthError(writer, err)
		return
	}
	writeJSON(writer, http.StatusOK, result)
}

func writeGitHubOAuthError(writer http.ResponseWriter, err error) {
	var oauthError GitHubOAuthError
	if errors.As(err, &oauthError) {
		status := oauthError.Status
		if status == 0 {
			status = http.StatusInternalServerError
		}
		code := oauthError.Code
		if code == "" {
			code = "github_oauth_failed"
		}
		message := oauthError.Message
		if message == "" {
			message = "GitHub OAuth request could not be completed"
		}
		writeError(writer, status, code, message)
		return
	}
	writeError(writer, http.StatusInternalServerError, "github_oauth_failed", "GitHub OAuth request could not be completed")
}
