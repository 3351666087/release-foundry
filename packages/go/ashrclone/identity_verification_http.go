package ashrclone

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"time"
)

func (server *HTTPServer) handleIdentityVerification(writer http.ResponseWriter, request *http.Request, action string) {
	writer.Header().Set("Cache-Control", "no-store")
	writer.Header().Set("Pragma", "no-cache")
	writer.Header().Set("X-Content-Type-Options", "nosniff")
	if server.identityVerification == nil {
		writeError(writer, http.StatusServiceUnavailable, "identity_verification_unavailable", "identity verification is not configured")
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
	channel := IdentityVerificationChannel(stringValue(body, "channel"))
	purpose := IdentityVerificationPurpose(stringValue(body, "purpose"))
	accountID := stringValue(body, "account_id")
	actorID := ""
	if purpose == IdentityVerificationBinding && accountID != "" {
		session, authenticated := server.resolveIdentityHTTPSession(writer, request, accountID)
		if !authenticated {
			return
		}
		actorID = session.ActorID
	}
	switch action {
	case "challenges":
		responsePolicy := server.identityVerificationResponsePolicy
		if responsePolicy == nil {
			writeError(writer, http.StatusServiceUnavailable, "identity_verification_policy_unavailable", "identity verification is not configured")
			return
		}
		startedAt := time.Now().UTC()
		identifier := stringValue(body, "identifier")
		subject := IdentityVerificationAbuseSubject{
			Operation:        "identity_verification_start",
			IdentifierDigest: server.identityVerification.digest("public-start", strings.TrimSpace(identifier)),
			AccountID:        accountID,
			IPAddress:        request.RemoteAddr,
			TenantID:         stringValue(body, "tenant_id"),
			DeviceID:         request.Header.Get("X-Device-ID"),
		}
		var result IdentityVerificationPublicResponse
		var err error
		result, err = responsePolicy.Execute(
			request.Context(),
			startedAt,
			subject,
			func(ctx context.Context) error {
				_, startErr := server.identityVerification.Start(ctx, IdentityVerificationStartRequest{
					Channel: channel, Identifier: identifier, Purpose: purpose,
					TenantID: stringValue(body, "tenant_id"), AccountID: accountID,
				})
				return startErr
			},
		)
		if err != nil {
			writeError(writer, http.StatusRequestTimeout, "request_cancelled", "request was cancelled")
			return
		}
		writeJSON(writer, http.StatusAccepted, result)
	case "verify":
		result, err := server.identityVerification.Complete(request.Context(), IdentityVerificationCompleteRequest{
			ChallengeID: stringValue(body, "challenge_id"), Code: stringValue(body, "code"),
			Channel: channel, Identifier: stringValue(body, "identifier"), Purpose: purpose,
			TenantID: stringValue(body, "tenant_id"), AccountID: accountID,
			ActorID: actorID, DisplayName: stringValue(body, "display_name"),
		})
		if err != nil {
			writeIdentityVerificationHTTPError(writer, err)
			return
		}
		writeJSON(writer, http.StatusOK, publicIdentityVerificationResult(result))
	default:
		writeError(writer, http.StatusNotFound, "not_found", "route not found")
	}
}

func publicIdentityVerificationResult(result IdentityVerificationResultDTO) JSONMap {
	return JSONMap{
		"schema_version":     result.SchemaVersion,
		"challenge_id":       result.ChallengeID,
		"channel":            result.Channel,
		"purpose":            result.Purpose,
		"tenant_id":          result.TenantID,
		"account":            publicIdentityAccount(result.Account),
		"credential":         publicIdentityCredentials([]IdentityCredentialDTO{result.Credential})[0],
		"credential_created": result.Created,
		"verified_at":        result.VerifiedAt,
	}
}

func writeIdentityVerificationHTTPError(writer http.ResponseWriter, err error) {
	var verification IdentityVerificationError
	var identity IdentityDomainError
	switch {
	case errors.Is(err, ErrIdentityVerificationNotFound), errors.Is(err, ErrIdentityVerificationConsumed):
		writeError(writer, http.StatusBadRequest, verificationErrorCode(err), "identity verification proof is invalid")
	case errors.As(err, &verification):
		status := http.StatusBadRequest
		if verification.Code == "verification_resend_cooldown" {
			status = http.StatusTooManyRequests
		}
		writeError(writer, status, verification.Code, verification.Error())
	case errors.As(err, &identity):
		status := http.StatusBadRequest
		if identity.Code == "credential_link_conflict" {
			status = http.StatusConflict
		}
		writeError(writer, status, identity.Code, identity.Error())
	default:
		writeError(writer, http.StatusInternalServerError, "identity_verification_failed", "identity verification failed")
	}
}
