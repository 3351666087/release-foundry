package ashrclone

import (
	"errors"
	"net/http"
)

type a3IdentityTwoFactorView struct {
	Status      string `json:"status"`
	Optional    bool   `json:"optional"`
	Recommended bool   `json:"recommended"`
}

type a3IdentityAccountView struct {
	AccountID      string                  `json:"account_id"`
	PasswordStatus string                  `json:"password_status"`
	TwoFactor      a3IdentityTwoFactorView `json:"two_factor"`
}

func a3IdentityAccount(account IdentityAccountDTO) a3IdentityAccountView {
	return a3IdentityAccountView{
		AccountID:      account.AccountID,
		PasswordStatus: account.SecurityPosture.Password.Status,
		TwoFactor: a3IdentityTwoFactorView{
			Status:   account.SecurityPosture.TwoFactor.Status,
			Optional: true, Recommended: true,
		},
	}
}

func a3IdentityProvider(provider IdentityProvider) IdentityProvider {
	if normalizeIdentityLifecycleProvider(provider) == IdentityProviderLocal {
		return "email"
	}
	return normalizeIdentityLifecycleProvider(provider)
}

func a3IdentitySecurity(proofRequired, enumerationSafe bool) JSONMap {
	return JSONMap{
		"server_verified_proof_required":   proofRequired,
		"recent_reauthentication_required": false,
		"csrf_required":                    false,
		"account_enumeration_safe":         enumerationSafe,
	}
}

func a3IdentityEnvelope(operation, status string, provider IdentityProvider, account any, nextAction string) JSONMap {
	return JSONMap{
		"schema_version": A3IdentitySchemaVersion,
		"operation":      operation, "status": status,
		"provider": a3IdentityProvider(provider),
		"account":  account, "next_action": nextAction,
		"security": a3IdentitySecurity(true, operation == "login_start" || operation == "login_complete"),
	}
}

var forbiddenPublicIdentityProofFields = []string{
	"verified",
	"identifier",
	"verified_email",
	"credential",
	"credential_id",
	"account_id",
}

func (server *HTTPServer) handleIdentityLifecycle(writer http.ResponseWriter, request *http.Request, parts []string) {
	writer.Header().Set("Cache-Control", "no-store")
	writer.Header().Set("Pragma", "no-cache")
	writer.Header().Set("X-Content-Type-Options", "nosniff")
	if server.identityLifecycle == nil {
		writeError(writer, http.StatusServiceUnavailable, "identity_lifecycle_unavailable", "identity lifecycle service is unavailable")
		return
	}
	if len(parts) == 1 && parts[0] == "providers" {
		if request.Method != http.MethodGet {
			writeError(writer, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
			return
		}
		providers := server.identityLifecycle.ProviderCapabilities()
		for index := range providers {
			providers[index].Provider = a3IdentityProvider(providers[index].Provider)
		}
		writeJSON(writer, http.StatusOK, JSONMap{
			"schema_version": A3IdentityProvidersSchemaVersion,
			"providers":      providers,
		})
		return
	}
	if len(parts) != 2 || (parts[0] != "registration" && parts[0] != "login") {
		writeError(writer, http.StatusNotFound, "not_found", "route not found")
		return
	}
	if request.Method != http.MethodPost {
		writeError(writer, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
		return
	}
	body, ok := readJSONBody(writer, request)
	if !ok {
		return
	}
	for _, field := range forbiddenPublicIdentityProofFields {
		if _, exists := body[field]; exists {
			writeError(writer, http.StatusBadRequest, "caller_verified_proof_rejected", "caller-controlled identity proof fields are not accepted")
			return
		}
	}
	operation := IdentityOperationRegistration
	if parts[0] == "login" {
		operation = IdentityOperationLogin
	}
	provider := normalizeIdentityLifecycleProvider(IdentityProvider(stringValue(body, "provider")))
	if provider == "" && stringValue(body, "kind") == "email" {
		provider = IdentityProviderLocal
	}
	switch parts[1] {
	case "start":
		inputs := map[string]string{}
		if value := stringValue(body, "email"); value != "" {
			inputs["email"] = value
		}
		if value := stringValue(body, "authorization_code"); value != "" {
			inputs["authorization_code"] = value
		}
		receipt, err := server.identityLifecycle.Start(request.Context(), TrustedIdentityProofRequest{
			Operation: operation, Provider: provider,
			TenantID: stringValue(body, "tenant_id"), ProjectID: stringValue(body, "project_id"),
			Inputs: inputs,
		})
		if err != nil {
			writeIdentityLifecycleHTTPError(writer, err, operation, provider)
			return
		}
		operationName := "register_start"
		if operation == IdentityOperationLogin {
			operationName = "login_start"
		}
		response := a3IdentityEnvelope(operationName, "verification_required", provider, nil, "complete_provider")
		response["receipt_id"] = receipt.ReceiptID
		response["expires_at"] = receipt.ExpiresAt
		writeJSON(writer, http.StatusCreated, response)
	case "complete":
		completion := CompleteIdentityLifecycleRequest{
			ReceiptID: stringValue(body, "receipt_id"), Provider: provider,
			TenantID: stringValue(body, "tenant_id"), ProjectID: stringValue(body, "project_id"),
		}
		if operation == IdentityOperationRegistration {
			account, err := server.identityLifecycle.CompleteRegistration(completion)
			if err != nil {
				writeIdentityLifecycleHTTPError(writer, err, operation, provider)
				return
			}
			nextAction := "none"
			if account.SecurityPosture.TwoFactor.Status == "disabled" {
				nextAction = "enroll_two_factor"
			}
			writeJSON(writer, http.StatusCreated,
				a3IdentityEnvelope("register_complete", "completed", provider, a3IdentityAccount(account), nextAction))
			return
		}
		authentication, err := server.identityLifecycle.CompleteLogin(completion)
		if err != nil {
			writeIdentityLifecycleHTTPError(writer, err, operation, provider)
			return
		}
		response := a3IdentityEnvelope("login_complete", "authenticated", provider,
			a3IdentityAccount(authentication.Account), "none")
		response["authenticated_at"] = authentication.Authenticated
		writeJSON(writer, http.StatusOK, response)
	default:
		writeError(writer, http.StatusNotFound, "not_found", "route not found")
	}
}

func writeIdentityLifecycleHTTPError(
	writer http.ResponseWriter,
	err error,
	operation IdentityLifecycleOperation,
	provider IdentityProvider,
) {
	if operation == IdentityOperationLogin {
		response := a3IdentityEnvelope("login_complete", "failed", provider, nil, "none")
		if !isPublicAuthenticationFailure(err) {
			response["error"] = JSONMap{
				"code": "provider_unavailable", "http_status": http.StatusServiceUnavailable,
				"anti_enumeration": true, "retryable": true, "public_safe": true,
			}
			writeJSON(writer, http.StatusServiceUnavailable, response)
			return
		}
		// Unknown credentials, wrong credentials, expired/replayed receipts, and
		// scope mismatches intentionally share one public response.
		response["error"] = JSONMap{
			"code": "authentication_failed", "http_status": http.StatusUnauthorized,
			"anti_enumeration": true, "retryable": false, "public_safe": true,
		}
		writeJSON(writer, http.StatusUnauthorized, response)
		return
	}
	var domain IdentityDomainError
	response := a3IdentityEnvelope("register_complete", "failed", provider, nil, "none")
	code := "provider_unavailable"
	status := http.StatusInternalServerError
	switch {
	case errors.Is(err, ErrIdentityProofReceiptNotFound),
		errors.Is(err, ErrIdentityProofReceiptConsumed),
		errors.Is(err, ErrIdentityProofReceiptExpired),
		errors.Is(err, ErrIdentityProofScopeMismatch):
		status = http.StatusBadRequest
		code = "verified_proof_required"
		if errors.Is(err, ErrIdentityProofReceiptConsumed) {
			code = "verified_proof_replayed"
		} else if errors.Is(err, ErrIdentityProofReceiptExpired) {
			code = "verified_proof_expired"
		} else if errors.Is(err, ErrIdentityProofScopeMismatch) {
			code = "verified_proof_scope_mismatch"
		}
	case errors.As(err, &domain):
		status = http.StatusBadRequest
		if domain.Code == "trusted_proof_provider_unavailable" ||
			domain.Code == "identity_provider_unavailable" {
			code = "provider_unavailable"
		} else {
			code = "verified_proof_required"
		}
	}
	response["error"] = JSONMap{
		"code": code, "http_status": status, "anti_enumeration": false,
		"retryable": false, "public_safe": true,
	}
	writeJSON(writer, status, response)
}

func isPublicAuthenticationFailure(err error) bool {
	if errors.Is(err, ErrIdentityProofReceiptNotFound) ||
		errors.Is(err, ErrIdentityProofReceiptConsumed) ||
		errors.Is(err, ErrIdentityProofReceiptExpired) ||
		errors.Is(err, ErrIdentityProofScopeMismatch) ||
		errors.Is(err, ErrIdentityCredentialNotFound) {
		return true
	}
	var domain IdentityDomainError
	if !errors.As(err, &domain) {
		return false
	}
	switch domain.Code {
	case "invalid_credential",
		"invalid_email",
		"invalid_phone",
		"credential_verification_required",
		"credential_not_login_capable":
		return true
	default:
		return false
	}
}
