package releasefoundry

import (
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const (
	IdentityBrowserVerificationSchemaVersion    = "releasefoundry.identity_browser_verification.v1"
	IdentityBrowserVerificationIntentCookieName = "__Host-releasefoundry_identity_intent"

	defaultIdentityBrowserIntentMaxLifetime = 15 * time.Minute
	maximumIdentityBrowserIntentMaxLifetime = 30 * time.Minute
	maximumIdentityBrowserIntentCookieBytes = 4096
)

var (
	errIdentityBrowserIntentUnavailable = errors.New("identity browser verification intent is unavailable")
	errIdentityBrowserIntentInvalid     = errors.New("identity browser verification intent is invalid")
)

// IdentityBrowserVerificationIntentIssue is trusted server-side state. Its
// String forms deliberately redact the normalized identifier.
type IdentityBrowserVerificationIntentIssue struct {
	ChallengeID string
	Purpose     IdentityVerificationPurpose
	TenantID    string
	ProjectID   string
	Identifier  string
	ExpiresAt   time.Time
}

func (issue IdentityBrowserVerificationIntentIssue) String() string {
	return fmt.Sprintf(
		"IdentityBrowserVerificationIntentIssue{challenge_id:%q,purpose:%q,tenant_id:%q,project_id:%q,identifier:<redacted>,expires_at:%q}",
		issue.ChallengeID,
		issue.Purpose,
		issue.TenantID,
		issue.ProjectID,
		issue.ExpiresAt.UTC().Format(time.RFC3339),
	)
}

func (issue IdentityBrowserVerificationIntentIssue) GoString() string {
	return issue.String()
}

type IdentityBrowserVerificationIntentReceipt struct {
	IntentID string
}

type IdentityBrowserVerificationIntentValidation struct {
	ChallengeID string
	IntentID    string
	Purpose     IdentityVerificationPurpose
	TenantID    string
	ProjectID   string
}

// IdentityBrowserVerificationIntentClaim contains the normalized email needed
// by the trusted completion coordinator. Its String forms never disclose it.
type IdentityBrowserVerificationIntentClaim struct {
	Identifier string
}

func (claim IdentityBrowserVerificationIntentClaim) String() string {
	if strings.TrimSpace(claim.Identifier) == "" {
		return "IdentityBrowserVerificationIntentClaim<empty>"
	}
	return "IdentityBrowserVerificationIntentClaim{identifier:<redacted>}"
}

func (claim IdentityBrowserVerificationIntentClaim) GoString() string {
	return claim.String()
}

// IdentityBrowserVerificationIntentTransport keeps raw email and proof material
// out of A3-visible cookies and responses. Implementations must validate HTTPS,
// exact same-origin browser metadata, purpose, tenant/project scope, challenge,
// intent identifier, and expiry before returning a claim.
type IdentityBrowserVerificationIntentTransport interface {
	IssueIdentityBrowserVerificationIntent(
		http.ResponseWriter,
		*http.Request,
		IdentityBrowserVerificationIntentIssue,
	) (IdentityBrowserVerificationIntentReceipt, error)
	ValidateIdentityBrowserVerificationIntent(
		*http.Request,
		IdentityBrowserVerificationIntentValidation,
	) (IdentityBrowserVerificationIntentClaim, error)
	ClearIdentityBrowserVerificationIntent(http.ResponseWriter)
}

type identityBrowserVerificationIntentCodec struct {
	aead        cipher.AEAD
	maxLifetime time.Duration
	now         func() time.Time
}

type identityBrowserVerificationIntentPayload struct {
	SchemaVersion string                      `json:"schema_version"`
	IntentID      string                      `json:"intent_id"`
	ChallengeID   string                      `json:"challenge_id"`
	Purpose       IdentityVerificationPurpose `json:"purpose"`
	TenantID      string                      `json:"tenant_id"`
	ProjectID     string                      `json:"project_id"`
	Identifier    string                      `json:"identifier"`
	Origin        string                      `json:"origin"`
	ExpiresAt     string                      `json:"expires_at"`
}

type identityBrowserEmailBeginRequest struct {
	Email string `json:"email"`
}

type identityBrowserRegistrationCompleteRequest struct {
	ChallengeID string `json:"challenge_id"`
	IntentID    string `json:"intent_id"`
	Proof       string `json:"proof"`
	DisplayName string `json:"display_name,omitempty"`
}

type identityBrowserLoginCompleteRequest struct {
	ChallengeID string `json:"challenge_id"`
	IntentID    string `json:"intent_id"`
	Proof       string `json:"proof"`
}

type identityBrowserChallengeResponse struct {
	SchemaVersion string    `json:"schema_version"`
	ChallengeID   string    `json:"challenge_id"`
	IntentID      string    `json:"intent_id"`
	ExpiresAt     time.Time `json:"expires_at"`
	ResendAfter   time.Time `json:"resend_after"`
}

func newIdentityBrowserVerificationIntentCodec(
	key []byte,
	maxLifetime time.Duration,
	now func() time.Time,
) (*identityBrowserVerificationIntentCodec, error) {
	if len(key) == 0 {
		return nil, nil
	}
	if len(key) < 32 {
		return nil, fmt.Errorf("identity browser verification intent key must contain at least 32 bytes")
	}
	if maxLifetime == 0 {
		maxLifetime = defaultIdentityBrowserIntentMaxLifetime
	}
	if maxLifetime < time.Second || maxLifetime > maximumIdentityBrowserIntentMaxLifetime {
		return nil, fmt.Errorf("identity browser verification intent max lifetime must be between one second and 30 minutes")
	}
	if now == nil {
		now = time.Now
	}
	mac := hmac.New(sha256.New, key)
	_, _ = mac.Write([]byte("releasefoundry.identity.browser_verification_intent.aead.v1"))
	derivedKey := mac.Sum(nil)
	block, err := aes.NewCipher(derivedKey)
	for index := range derivedKey {
		derivedKey[index] = 0
	}
	if err != nil {
		return nil, fmt.Errorf("configure identity browser verification intent cipher: %w", err)
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("configure identity browser verification intent AEAD: %w", err)
	}
	return &identityBrowserVerificationIntentCodec{
		aead:        aead,
		maxLifetime: maxLifetime,
		now:         now,
	}, nil
}

func (transport *IdentitySessionCookieTransport) IssueIdentityBrowserVerificationIntent(
	writer http.ResponseWriter,
	request *http.Request,
	issue IdentityBrowserVerificationIntentIssue,
) (IdentityBrowserVerificationIntentReceipt, error) {
	if transport == nil || transport.browserIntent == nil || writer == nil {
		return IdentityBrowserVerificationIntentReceipt{}, errIdentityBrowserIntentUnavailable
	}
	if err := transport.ValidateIdentitySessionRequest(request); err != nil {
		return IdentityBrowserVerificationIntentReceipt{}, err
	}
	origin, err := identityBrowserVerificationOrigin(request)
	if err != nil {
		return IdentityBrowserVerificationIntentReceipt{}, errIdentityBrowserIntentInvalid
	}
	now := transport.browserIntent.now().UTC()
	expiresAt := issue.ExpiresAt.UTC()
	if !validIdentityBrowserVerificationIntentIssue(issue) ||
		!expiresAt.After(now) ||
		expiresAt.After(now.Add(transport.browserIntent.maxLifetime)) {
		return IdentityBrowserVerificationIntentReceipt{}, errIdentityBrowserIntentInvalid
	}
	intentRaw := make([]byte, 24)
	if _, err := io.ReadFull(rand.Reader, intentRaw); err != nil {
		return IdentityBrowserVerificationIntentReceipt{}, errIdentityBrowserIntentUnavailable
	}
	intentID := "ivi_" + base64.RawURLEncoding.EncodeToString(intentRaw)
	payload, err := json.Marshal(identityBrowserVerificationIntentPayload{
		SchemaVersion: IdentityBrowserVerificationSchemaVersion,
		IntentID:      intentID,
		ChallengeID:   issue.ChallengeID,
		Purpose:       issue.Purpose,
		TenantID:      issue.TenantID,
		ProjectID:     issue.ProjectID,
		Identifier:    issue.Identifier,
		Origin:        origin,
		ExpiresAt:     expiresAt.Format(time.RFC3339Nano),
	})
	if err != nil {
		return IdentityBrowserVerificationIntentReceipt{}, errIdentityBrowserIntentUnavailable
	}
	nonce := make([]byte, transport.browserIntent.aead.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return IdentityBrowserVerificationIntentReceipt{}, errIdentityBrowserIntentUnavailable
	}
	sealed := transport.browserIntent.aead.Seal(
		nonce,
		nonce,
		payload,
		[]byte(IdentityBrowserVerificationIntentCookieName+"|v1"),
	)
	cookieValue := "v1." + base64.RawURLEncoding.EncodeToString(sealed)
	maxAge := int(expiresAt.Sub(now) / time.Second)
	if len(cookieValue) > maximumIdentityBrowserIntentCookieBytes || maxAge < 1 {
		return IdentityBrowserVerificationIntentReceipt{}, errIdentityBrowserIntentInvalid
	}
	cookie := &http.Cookie{
		Name:     IdentityBrowserVerificationIntentCookieName,
		Value:    cookieValue,
		Path:     "/",
		Expires:  expiresAt,
		MaxAge:   maxAge,
		Secure:   true,
		HttpOnly: true,
		SameSite: http.SameSiteStrictMode,
	}
	if err := cookie.Valid(); err != nil {
		return IdentityBrowserVerificationIntentReceipt{}, errIdentityBrowserIntentInvalid
	}
	http.SetCookie(writer, cookie)
	return IdentityBrowserVerificationIntentReceipt{IntentID: intentID}, nil
}

func (transport *IdentitySessionCookieTransport) ValidateIdentityBrowserVerificationIntent(
	request *http.Request,
	expected IdentityBrowserVerificationIntentValidation,
) (IdentityBrowserVerificationIntentClaim, error) {
	if transport == nil || transport.browserIntent == nil {
		return IdentityBrowserVerificationIntentClaim{}, errIdentityBrowserIntentUnavailable
	}
	if err := transport.ValidateIdentitySessionRequest(request); err != nil {
		return IdentityBrowserVerificationIntentClaim{}, err
	}
	origin, err := identityBrowserVerificationOrigin(request)
	if err != nil || !validIdentityBrowserVerificationIntentValidation(expected) {
		return IdentityBrowserVerificationIntentClaim{}, errIdentityBrowserIntentInvalid
	}
	cookie, err := uniqueIdentityBrowserVerificationIntentCookie(request)
	if err != nil {
		return IdentityBrowserVerificationIntentClaim{}, errIdentityBrowserIntentInvalid
	}
	parts := strings.Split(cookie.Value, ".")
	if len(parts) != 2 || parts[0] != "v1" ||
		len(cookie.Value) > maximumIdentityBrowserIntentCookieBytes {
		return IdentityBrowserVerificationIntentClaim{}, errIdentityBrowserIntentInvalid
	}
	sealed, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil || len(sealed) <= transport.browserIntent.aead.NonceSize() {
		return IdentityBrowserVerificationIntentClaim{}, errIdentityBrowserIntentInvalid
	}
	if !constantTimeIdentityBrowserValue(
		base64.RawURLEncoding.EncodeToString(sealed),
		parts[1],
	) {
		return IdentityBrowserVerificationIntentClaim{}, errIdentityBrowserIntentInvalid
	}
	nonceSize := transport.browserIntent.aead.NonceSize()
	plaintext, err := transport.browserIntent.aead.Open(
		nil,
		sealed[:nonceSize],
		sealed[nonceSize:],
		[]byte(IdentityBrowserVerificationIntentCookieName+"|v1"),
	)
	if err != nil {
		return IdentityBrowserVerificationIntentClaim{}, errIdentityBrowserIntentInvalid
	}
	var payload identityBrowserVerificationIntentPayload
	if err := json.Unmarshal(plaintext, &payload); err != nil {
		return IdentityBrowserVerificationIntentClaim{}, errIdentityBrowserIntentInvalid
	}
	expiresAt, err := time.Parse(time.RFC3339Nano, payload.ExpiresAt)
	if err != nil || !expiresAt.After(transport.browserIntent.now().UTC()) {
		return IdentityBrowserVerificationIntentClaim{}, errIdentityBrowserIntentInvalid
	}
	if payload.SchemaVersion != IdentityBrowserVerificationSchemaVersion ||
		!constantTimeIdentityBrowserValue(payload.IntentID, expected.IntentID) ||
		!constantTimeIdentityBrowserValue(payload.ChallengeID, expected.ChallengeID) ||
		!constantTimeIdentityBrowserValue(string(payload.Purpose), string(expected.Purpose)) ||
		!constantTimeIdentityBrowserValue(payload.TenantID, expected.TenantID) ||
		!constantTimeIdentityBrowserValue(payload.ProjectID, expected.ProjectID) ||
		!constantTimeIdentityBrowserValue(payload.Origin, origin) {
		return IdentityBrowserVerificationIntentClaim{}, errIdentityBrowserIntentInvalid
	}
	normalized, normalizeErr := normalizeIdentityEmail(payload.Identifier)
	if normalizeErr != nil ||
		!constantTimeIdentityBrowserValue(normalized, payload.Identifier) {
		return IdentityBrowserVerificationIntentClaim{}, errIdentityBrowserIntentInvalid
	}
	return IdentityBrowserVerificationIntentClaim{Identifier: normalized}, nil
}

func (transport *IdentitySessionCookieTransport) ClearIdentityBrowserVerificationIntent(
	writer http.ResponseWriter,
) {
	clearIdentityBrowserVerificationIntentCookie(writer)
}

func clearIdentityBrowserVerificationIntentCookie(writer http.ResponseWriter) {
	if writer == nil {
		return
	}
	http.SetCookie(writer, &http.Cookie{
		Name:     IdentityBrowserVerificationIntentCookieName,
		Path:     "/",
		Expires:  time.Unix(1, 0).UTC(),
		MaxAge:   -1,
		Secure:   true,
		HttpOnly: true,
		SameSite: http.SameSiteStrictMode,
	})
}

func uniqueIdentityBrowserVerificationIntentCookie(
	request *http.Request,
) (*http.Cookie, error) {
	if request == nil {
		return nil, errIdentityBrowserIntentInvalid
	}
	var result *http.Cookie
	for _, cookie := range request.Cookies() {
		if cookie.Name != IdentityBrowserVerificationIntentCookieName {
			continue
		}
		if result != nil || strings.TrimSpace(cookie.Value) != cookie.Value ||
			cookie.Value == "" {
			return nil, errIdentityBrowserIntentInvalid
		}
		copyCookie := *cookie
		result = &copyCookie
	}
	if result == nil {
		return nil, errIdentityBrowserIntentInvalid
	}
	return result, nil
}

func validIdentityBrowserVerificationIntentIssue(
	issue IdentityBrowserVerificationIntentIssue,
) bool {
	if !validIdentityBrowserVerificationPurpose(issue.Purpose) ||
		!validIdentityBrowserVerificationHandle(issue.ChallengeID, 256) ||
		!validIdentityBrowserVerificationHandle(issue.TenantID, 256) ||
		!validIdentityBrowserVerificationHandle(issue.ProjectID, 256) {
		return false
	}
	normalized, err := normalizeIdentityEmail(issue.Identifier)
	return err == nil && constantTimeIdentityBrowserValue(normalized, issue.Identifier)
}

func validIdentityBrowserVerificationIntentValidation(
	expected IdentityBrowserVerificationIntentValidation,
) bool {
	return validIdentityBrowserVerificationPurpose(expected.Purpose) &&
		validIdentityBrowserVerificationHandle(expected.ChallengeID, 256) &&
		validIdentityBrowserVerificationHandle(expected.IntentID, 256) &&
		validIdentityBrowserVerificationHandle(expected.TenantID, 256) &&
		validIdentityBrowserVerificationHandle(expected.ProjectID, 256)
}

func validIdentityBrowserVerificationPurpose(
	purpose IdentityVerificationPurpose,
) bool {
	return purpose == IdentityVerificationRegistration ||
		purpose == IdentityVerificationLogin
}

func validIdentityBrowserVerificationHandle(value string, maximum int) bool {
	return value != "" && value == strings.TrimSpace(value) &&
		len(value) <= maximum && !strings.ContainsAny(value, "\x00\r\n\t")
}

func constantTimeIdentityBrowserValue(left string, right string) bool {
	return subtle.ConstantTimeCompare([]byte(left), []byte(right)) == 1
}

func identityBrowserVerificationOrigin(request *http.Request) (string, error) {
	if request == nil || request.Host == "" ||
		request.Host != strings.TrimSpace(request.Host) {
		return "", errIdentityBrowserIntentInvalid
	}
	originValues := request.Header.Values("Origin")
	if len(originValues) != 1 ||
		originValues[0] == "" ||
		originValues[0] != strings.TrimSpace(originValues[0]) ||
		strings.Contains(originValues[0], ",") {
		return "", errIdentityBrowserIntentInvalid
	}
	origin, err := url.Parse(originValues[0])
	if err != nil ||
		!strings.EqualFold(origin.Scheme, "https") ||
		origin.Host == "" ||
		!strings.EqualFold(origin.Host, request.Host) ||
		origin.User != nil ||
		origin.Path != "" ||
		origin.RawQuery != "" ||
		origin.Fragment != "" {
		return "", errIdentityBrowserIntentInvalid
	}
	fetchSite := request.Header.Values("Sec-Fetch-Site")
	if len(fetchSite) > 1 ||
		(len(fetchSite) == 1 &&
			(fetchSite[0] != strings.TrimSpace(fetchSite[0]) ||
				!strings.EqualFold(fetchSite[0], "same-origin"))) {
		return "", errIdentityBrowserIntentInvalid
	}
	return "https://" + strings.ToLower(origin.Host), nil
}

func (service *IdentityVerificationService) identityBrowserVerificationScope() (
	string,
	string,
	bool,
) {
	if service == nil || service.productionOutboxStore == nil {
		return "", "", false
	}
	tenantID, projectID := service.productionOutboxStore.IdentityVerificationDeliveryScope()
	tenantID = strings.TrimSpace(tenantID)
	projectID = strings.TrimSpace(projectID)
	if !validIdentityBrowserVerificationHandle(tenantID, 256) ||
		!validIdentityBrowserVerificationHandle(projectID, 256) {
		return "", "", false
	}
	return tenantID, projectID, true
}

func (service *IdentityVerificationService) decoyIdentityBrowserChallenge(
	purpose IdentityVerificationPurpose,
	tenantID string,
) (IdentityVerificationChallengeDTO, error) {
	if service == nil {
		return IdentityVerificationChallengeDTO{}, errIdentityBrowserIntentUnavailable
	}
	challengeID, err := service.newChallengeID()
	if err != nil {
		return IdentityVerificationChallengeDTO{}, errIdentityBrowserIntentUnavailable
	}
	now := service.now().UTC()
	return IdentityVerificationChallengeDTO{
		SchemaVersion: IdentityVerificationSchemaVersion,
		ChallengeID:   challengeID,
		Channel:       IdentityVerificationEmail,
		Purpose:       purpose,
		TenantID:      tenantID,
		AccountBound:  false,
		ExpiresAt:     now.Add(service.ttl),
		ResendAfter:   now.Add(service.resendCooldown),
	}, nil
}

func (server *HTTPServer) handleIdentityBrowserEmailBegin(
	writer http.ResponseWriter,
	request *http.Request,
	purpose IdentityVerificationPurpose,
) {
	setIdentityBrowserVerificationHeaders(writer)
	if !requireIdentityMethod(writer, request, http.MethodPost) {
		return
	}
	if !validIdentityBrowserVerificationPurpose(purpose) ||
		server.identityVerification == nil ||
		server.identityVerificationResponsePolicy == nil ||
		server.identitySessionReceiptTransport == nil ||
		server.identityBrowserVerificationIntents == nil {
		writeIdentityError(
			writer,
			http.StatusServiceUnavailable,
			"identity_browser_verification_unavailable",
			"identity browser verification is not configured",
		)
		return
	}
	tenantID, projectID, ok := server.identityVerification.identityBrowserVerificationScope()
	if !ok {
		writeIdentityError(
			writer,
			http.StatusServiceUnavailable,
			"identity_browser_verification_scope_unavailable",
			"identity browser verification is not configured",
		)
		return
	}
	if err := server.identitySessionReceiptTransport.ValidateIdentitySessionRequest(request); err != nil {
		writeIdentityError(
			writer,
			http.StatusUpgradeRequired,
			"identity_browser_secure_transport_required",
			"identity browser verification requires HTTPS",
		)
		return
	}
	if _, err := identityBrowserVerificationOrigin(request); err != nil {
		writeIdentityError(
			writer,
			http.StatusForbidden,
			"identity_browser_origin_rejected",
			"identity browser verification origin was rejected",
		)
		return
	}
	if request.URL.RawQuery != "" {
		writeIdentityError(
			writer,
			http.StatusBadRequest,
			"identity_browser_request_invalid",
			"identity browser verification request is invalid",
		)
		return
	}
	var body identityBrowserEmailBeginRequest
	if !decodeIdentityJSON(writer, request, &body) {
		return
	}

	startedAt := time.Now().UTC()
	subject := IdentityVerificationAbuseSubject{
		Operation: "identity_browser_email_begin",
		IdentifierDigest: server.identityVerification.digest(
			"browser-public-start",
			string(purpose),
			strings.TrimSpace(body.Email),
		),
		IPAddress: request.RemoteAddr,
		TenantID:  tenantID,
		DeviceID:  request.Header.Get("X-Device-ID"),
	}
	var challenge IdentityVerificationChallengeDTO
	_, err := server.identityVerificationResponsePolicy.Execute(
		request.Context(),
		startedAt,
		subject,
		func(ctx context.Context) error {
			started, startErr := server.identityVerification.Start(
				ctx,
				IdentityVerificationStartRequest{
					Channel:    IdentityVerificationEmail,
					Identifier: body.Email,
					Purpose:    purpose,
					TenantID:   tenantID,
				},
			)
			if startErr == nil {
				challenge = started
			}
			return startErr
		},
	)
	if err != nil {
		writeIdentityError(
			writer,
			http.StatusRequestTimeout,
			"request_cancelled",
			"request was cancelled",
		)
		return
	}
	normalizedEmail, normalizeErr := normalizeIdentityEmail(body.Email)
	if challenge.ChallengeID == "" {
		challenge, err = server.identityVerification.decoyIdentityBrowserChallenge(
			purpose,
			tenantID,
		)
		if err != nil {
			writeIdentityError(
				writer,
				http.StatusServiceUnavailable,
				"identity_browser_verification_unavailable",
				"identity browser verification is temporarily unavailable",
			)
			return
		}
		normalizedEmail = "browser-decoy@invalid.example"
	} else if normalizeErr != nil {
		writeIdentityError(
			writer,
			http.StatusServiceUnavailable,
			"identity_browser_verification_unavailable",
			"identity browser verification is temporarily unavailable",
		)
		return
	}
	intentReceipt, err := server.identityBrowserVerificationIntents.
		IssueIdentityBrowserVerificationIntent(
			writer,
			request,
			IdentityBrowserVerificationIntentIssue{
				ChallengeID: challenge.ChallengeID,
				Purpose:     purpose,
				TenantID:    tenantID,
				ProjectID:   projectID,
				Identifier:  normalizedEmail,
				ExpiresAt:   challenge.ExpiresAt,
			},
		)
	if err != nil {
		writeIdentityError(
			writer,
			http.StatusServiceUnavailable,
			"identity_browser_intent_unavailable",
			"identity browser verification is temporarily unavailable",
		)
		return
	}
	writeJSON(writer, http.StatusAccepted, identityBrowserChallengeResponse{
		SchemaVersion: IdentityBrowserVerificationSchemaVersion,
		ChallengeID:   challenge.ChallengeID,
		IntentID:      intentReceipt.IntentID,
		ExpiresAt:     challenge.ExpiresAt,
		ResendAfter:   challenge.ResendAfter,
	})
}

func (server *HTTPServer) handleIdentityBrowserEmailComplete(
	writer http.ResponseWriter,
	request *http.Request,
	purpose IdentityVerificationPurpose,
) {
	setIdentityBrowserVerificationHeaders(writer)
	if !requireIdentityMethod(writer, request, http.MethodPost) {
		return
	}
	if !validIdentityBrowserVerificationPurpose(purpose) ||
		server.identityVerification == nil ||
		server.identitySessionReceiptTransport == nil ||
		server.identityBrowserVerificationIntents == nil {
		writeIdentityError(
			writer,
			http.StatusServiceUnavailable,
			"identity_browser_verification_unavailable",
			"identity browser verification is not configured",
		)
		return
	}
	tenantID, projectID, ok := server.identityVerification.identityBrowserVerificationScope()
	if !ok {
		writeIdentityError(
			writer,
			http.StatusServiceUnavailable,
			"identity_browser_verification_scope_unavailable",
			"identity browser verification is not configured",
		)
		return
	}
	if err := server.identitySessionReceiptTransport.ValidateIdentitySessionRequest(request); err != nil {
		writeIdentityError(
			writer,
			http.StatusUpgradeRequired,
			"identity_browser_secure_transport_required",
			"identity browser verification requires HTTPS",
		)
		return
	}
	if _, err := identityBrowserVerificationOrigin(request); err != nil {
		writeIdentityError(
			writer,
			http.StatusForbidden,
			"identity_browser_origin_rejected",
			"identity browser verification origin was rejected",
		)
		return
	}
	if request.URL.RawQuery != "" {
		writeIdentityError(
			writer,
			http.StatusBadRequest,
			"identity_browser_request_invalid",
			"identity browser verification request is invalid",
		)
		return
	}

	var challengeID string
	var intentID string
	var proof string
	var displayName string
	switch purpose {
	case IdentityVerificationRegistration:
		var body identityBrowserRegistrationCompleteRequest
		if !decodeIdentityJSON(writer, request, &body) {
			return
		}
		challengeID = strings.TrimSpace(body.ChallengeID)
		intentID = strings.TrimSpace(body.IntentID)
		proof = body.Proof
		displayName = body.DisplayName
	case IdentityVerificationLogin:
		var body identityBrowserLoginCompleteRequest
		if !decodeIdentityJSON(writer, request, &body) {
			return
		}
		challengeID = strings.TrimSpace(body.ChallengeID)
		intentID = strings.TrimSpace(body.IntentID)
		proof = body.Proof
	default:
		writeIdentityError(
			writer,
			http.StatusBadRequest,
			"identity_browser_request_invalid",
			"identity browser verification request is invalid",
		)
		return
	}

	claim, err := server.identityBrowserVerificationIntents.
		ValidateIdentityBrowserVerificationIntent(
			request,
			IdentityBrowserVerificationIntentValidation{
				ChallengeID: challengeID,
				IntentID:    intentID,
				Purpose:     purpose,
				TenantID:    tenantID,
				ProjectID:   projectID,
			},
		)
	if err != nil {
		writeIdentityError(
			writer,
			http.StatusForbidden,
			"identity_browser_intent_rejected",
			"identity browser verification intent was rejected",
		)
		return
	}
	_, receipt, err := server.identityVerification.CompleteAndIssueSession(
		request.Context(),
		IdentityVerificationCompleteRequest{
			ChallengeID: challengeID,
			Code:        proof,
			Channel:     IdentityVerificationEmail,
			Identifier:  claim.Identifier,
			Purpose:     purpose,
			TenantID:    tenantID,
			DisplayName: displayName,
		},
	)
	if err != nil {
		writeIdentityError(
			writer,
			http.StatusBadRequest,
			"identity_browser_verification_failed",
			"identity browser verification could not be completed",
		)
		return
	}
	if err := server.identitySessionReceiptTransport.WriteIdentitySessionReceipt(
		writer,
		request,
		receipt,
	); err != nil {
		writeIdentityError(
			writer,
			http.StatusInternalServerError,
			"identity_session_handoff_failed",
			"identity session handoff failed",
		)
		return
	}
	server.identityBrowserVerificationIntents.ClearIdentityBrowserVerificationIntent(writer)
	writer.Header().Set("Location", "/console")
	writer.Header().Del("Content-Type")
	writer.WriteHeader(http.StatusSeeOther)
}

func setIdentityBrowserVerificationHeaders(writer http.ResponseWriter) {
	writer.Header().Set("Cache-Control", "no-store")
	writer.Header().Set("Pragma", "no-cache")
	writer.Header().Set("X-Content-Type-Options", "nosniff")
}

var _ IdentityBrowserVerificationIntentTransport = (*IdentitySessionCookieTransport)(nil)
