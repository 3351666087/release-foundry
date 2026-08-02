package releasefoundry

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/netip"
	"net/url"
	"strings"
	"time"
)

const (
	IdentitySessionCookieName               = "__Host-releasefoundry_session"
	IdentityRefreshCookieName               = "__Host-releasefoundry_refresh"
	defaultIdentitySessionCookieMaxLifetime = 24 * time.Hour
	maximumIdentitySessionCookieMaxLifetime = 24 * time.Hour
	defaultIdentityRefreshCookieMaxLifetime = 30 * 24 * time.Hour
	maximumIdentityRefreshCookieMaxLifetime = 90 * 24 * time.Hour
)

var (
	errIdentitySessionSecureTransportRequired = errors.New("identity session handoff requires a secure transport")
	errIdentitySessionReceiptInvalid          = errors.New("identity session receipt is invalid")
)

// IdentitySessionReceiptTransport is the trusted boundary that may consume a
// one-use session receipt. Implementations must validate transport security
// before CompleteAndIssueSession mutates durable state.
type IdentitySessionReceiptTransport interface {
	ValidateIdentitySessionRequest(*http.Request) error
	WriteIdentitySessionReceipt(http.ResponseWriter, *http.Request, IdentitySessionIssuanceReceipt) error
}

type IdentitySessionCookieTransportOptions struct {
	Now                func() time.Time
	MaxLifetime        time.Duration
	RefreshMaxLifetime time.Duration
	TrustedProxyCIDRs  []netip.Prefix
	IntentKey          []byte
	IntentMaxLifetime  time.Duration
}

// IdentitySessionCookieTransport writes a host-only secure cookie. Forwarded
// scheme headers are considered only when the immediate peer is explicitly
// covered by a configured proxy CIDR.
type IdentitySessionCookieTransport struct {
	now                   func() time.Time
	maxLifetime           time.Duration
	refreshMaxLifetime    time.Duration
	trustedProxyCIDRs     []netip.Prefix
	browserIntent         *identityBrowserVerificationIntentCodec
	oauthFirstLoginIntent *oauthFirstLoginIntentCodec
}

func NewIdentitySessionCookieTransport(
	options IdentitySessionCookieTransportOptions,
) (*IdentitySessionCookieTransport, error) {
	maxLifetime := options.MaxLifetime
	if maxLifetime == 0 {
		maxLifetime = defaultIdentitySessionCookieMaxLifetime
	}
	if maxLifetime < time.Second || maxLifetime > maximumIdentitySessionCookieMaxLifetime {
		return nil, fmt.Errorf("identity session cookie max lifetime must be between one second and 24 hours")
	}
	refreshMaxLifetime := options.RefreshMaxLifetime
	if refreshMaxLifetime == 0 {
		refreshMaxLifetime = defaultIdentityRefreshCookieMaxLifetime
	}
	if refreshMaxLifetime < time.Second ||
		refreshMaxLifetime > maximumIdentityRefreshCookieMaxLifetime {
		return nil, fmt.Errorf("identity refresh cookie max lifetime must be between one second and 90 days")
	}
	now := options.Now
	if now == nil {
		now = time.Now
	}
	trustedProxyCIDRs := make([]netip.Prefix, 0, len(options.TrustedProxyCIDRs))
	for _, prefix := range options.TrustedProxyCIDRs {
		if !prefix.IsValid() {
			return nil, fmt.Errorf("identity session trusted proxy CIDR is invalid")
		}
		trustedProxyCIDRs = append(trustedProxyCIDRs, prefix.Masked())
	}
	browserIntent, err := newIdentityBrowserVerificationIntentCodec(
		options.IntentKey,
		options.IntentMaxLifetime,
		now,
	)
	if err != nil {
		return nil, err
	}
	oauthFirstLoginIntent, err := newOAuthFirstLoginIntentCodec(
		options.IntentKey,
		options.IntentMaxLifetime,
		now,
	)
	if err != nil {
		return nil, err
	}
	return &IdentitySessionCookieTransport{
		now:                   now,
		maxLifetime:           maxLifetime,
		refreshMaxLifetime:    refreshMaxLifetime,
		trustedProxyCIDRs:     trustedProxyCIDRs,
		browserIntent:         browserIntent,
		oauthFirstLoginIntent: oauthFirstLoginIntent,
	}, nil
}

func (transport *IdentitySessionCookieTransport) ValidateIdentitySessionRequest(
	request *http.Request,
) error {
	if transport == nil || request == nil {
		return errIdentitySessionSecureTransportRequired
	}
	if request.TLS != nil {
		return nil
	}
	remoteIP, ok := identitySessionRemoteIP(request.RemoteAddr)
	if !ok || !transport.trustsProxy(remoteIP) {
		return errIdentitySessionSecureTransportRequired
	}
	forwardedProto := request.Header.Values("X-Forwarded-Proto")
	if len(forwardedProto) != 1 ||
		!strings.EqualFold(strings.TrimSpace(forwardedProto[0]), "https") ||
		strings.Contains(forwardedProto[0], ",") {
		return errIdentitySessionSecureTransportRequired
	}
	return nil
}

func (transport *IdentitySessionCookieTransport) WriteIdentitySessionReceipt(
	writer http.ResponseWriter,
	request *http.Request,
	receipt IdentitySessionIssuanceReceipt,
) error {
	if writer == nil {
		return errIdentitySessionReceiptInvalid
	}
	if err := transport.ValidateIdentitySessionRequest(request); err != nil {
		return err
	}
	now := transport.now().UTC()
	accessExpiresAt := receipt.ExpiresAt().UTC()
	maximumAccessExpiresAt := now.Add(transport.maxLifetime)
	if accessExpiresAt.After(maximumAccessExpiresAt) {
		accessExpiresAt = maximumAccessExpiresAt
	}
	refreshExpiresAt := receipt.RefreshExpiresAt().UTC()
	maximumRefreshExpiresAt := now.Add(transport.refreshMaxLifetime)
	if refreshExpiresAt.After(maximumRefreshExpiresAt) {
		refreshExpiresAt = maximumRefreshExpiresAt
	}
	accessMaxAge := int(accessExpiresAt.Sub(now) / time.Second)
	refreshMaxAge := int(refreshExpiresAt.Sub(now) / time.Second)
	if receipt.SessionID() == "" || receipt.KeyVersion() == "" ||
		receipt.RefreshKeyVersion() == "" || accessMaxAge < 1 || refreshMaxAge < 1 ||
		!refreshExpiresAt.After(accessExpiresAt) {
		return errIdentitySessionReceiptInvalid
	}
	accessBearer, refreshBearer, err := receipt.TakeBearerTokens()
	if err != nil || accessBearer == "" || refreshBearer == "" {
		return errIdentitySessionReceiptInvalid
	}
	accessCookie := &http.Cookie{
		Name:     IdentitySessionCookieName,
		Value:    accessBearer,
		Path:     "/",
		Expires:  accessExpiresAt,
		MaxAge:   accessMaxAge,
		Secure:   true,
		HttpOnly: true,
		SameSite: http.SameSiteStrictMode,
	}
	refreshCookie := &http.Cookie{
		Name:     IdentityRefreshCookieName,
		Value:    refreshBearer,
		Path:     "/",
		Expires:  refreshExpiresAt,
		MaxAge:   refreshMaxAge,
		Secure:   true,
		HttpOnly: true,
		SameSite: http.SameSiteStrictMode,
	}
	if err := accessCookie.Valid(); err != nil {
		return errIdentitySessionReceiptInvalid
	}
	if err := refreshCookie.Valid(); err != nil {
		return errIdentitySessionReceiptInvalid
	}
	http.SetCookie(writer, accessCookie)
	http.SetCookie(writer, refreshCookie)
	return nil
}

func (transport *IdentitySessionCookieTransport) trustsProxy(address netip.Addr) bool {
	address = address.Unmap()
	for _, prefix := range transport.trustedProxyCIDRs {
		if prefix.Contains(address) {
			return true
		}
	}
	return false
}

func identitySessionRemoteIP(remoteAddress string) (netip.Addr, bool) {
	remoteAddress = strings.TrimSpace(remoteAddress)
	if addressPort, err := netip.ParseAddrPort(remoteAddress); err == nil {
		return addressPort.Addr().Unmap(), true
	}
	host, _, err := net.SplitHostPort(remoteAddress)
	if err != nil {
		host = remoteAddress
	}
	address, err := netip.ParseAddr(strings.Trim(host, "[]"))
	if err != nil {
		return netip.Addr{}, false
	}
	return address.Unmap(), true
}

func (server *HTTPServer) handleIdentitySessionRefresh(
	writer http.ResponseWriter,
	request *http.Request,
	projectID string,
	accountID string,
) {
	writer.Header().Set("Cache-Control", "no-store")
	writer.Header().Set("Pragma", "no-cache")
	writer.Header().Set("X-Content-Type-Options", "nosniff")
	if request.Method != http.MethodPost {
		writeError(writer, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
		return
	}
	refresher, ok := server.identitySessions.(IdentityHTTPSessionRefresher)
	if !ok || refresher == nil || server.identitySessionReceiptTransport == nil {
		writeError(writer, http.StatusServiceUnavailable, "identity_session_refresh_unavailable", "identity session refresh is not configured")
		return
	}
	if err := server.identitySessionReceiptTransport.ValidateIdentitySessionRequest(request); err != nil {
		writeError(writer, http.StatusUpgradeRequired, "identity_session_secure_transport_required", "identity session refresh requires HTTPS")
		return
	}
	if err := validateIdentitySessionRefreshBrowserRequest(request); err != nil {
		writeError(writer, http.StatusForbidden, "identity_session_refresh_origin_rejected", "identity session refresh origin was rejected")
		return
	}
	if request.URL.RawQuery != "" || len(request.TransferEncoding) != 0 ||
		(request.Body != nil && request.Body != http.NoBody && request.ContentLength != 0) {
		writeError(writer, http.StatusBadRequest, "identity_session_refresh_request_invalid", "identity session refresh request is invalid")
		return
	}
	idempotencyKey, err := identitySessionRefreshIdempotencyKey(request)
	if err != nil {
		writeError(writer, http.StatusBadRequest, "identity_session_refresh_idempotency_required", "identity session refresh requires a valid idempotency key")
		return
	}
	receipt, err := refresher.RefreshIdentityHTTPSession(
		request.Context(), request, projectID, accountID, idempotencyKey,
	)
	if err != nil {
		if errors.Is(err, ErrIdentitySessionRefreshReused) {
			clearIdentitySessionCookies(writer)
			writeError(writer, http.StatusConflict, "identity_session_refresh_reused", "identity session refresh credential was reused")
			return
		}
		writeError(writer, http.StatusUnauthorized, "identity_session_refresh_invalid", "identity session refresh could not be authenticated")
		return
	}
	if err := server.identitySessionReceiptTransport.WriteIdentitySessionReceipt(
		writer, request, receipt,
	); err != nil {
		writeError(writer, http.StatusInternalServerError, "identity_session_handoff_failed", "identity session handoff failed")
		return
	}
	writeJSON(writer, http.StatusOK, JSONMap{
		"schema_version": "releasefoundry.identity_session_refresh.v1",
		"status":         "rotated",
	})
}

func identitySessionRefreshIdempotencyKey(request *http.Request) (string, error) {
	values := request.Header.Values("Idempotency-Key")
	if len(values) != 1 {
		return "", ErrIdentitySessionRefreshInvalid
	}
	value := strings.TrimSpace(values[0])
	if value != values[0] || !validIdentitySessionIdempotencyKey(value) {
		return "", ErrIdentitySessionRefreshInvalid
	}
	return value, nil
}

func validateIdentitySessionRefreshBrowserRequest(request *http.Request) error {
	if request == nil || request.Host == "" {
		return ErrIdentitySessionRefreshInvalid
	}
	originValues := request.Header.Values("Origin")
	if len(originValues) != 1 || originValues[0] != strings.TrimSpace(originValues[0]) {
		return ErrIdentitySessionRefreshInvalid
	}
	origin, err := url.Parse(originValues[0])
	if err != nil || origin.Scheme != "https" || origin.Host == "" ||
		!strings.EqualFold(origin.Host, request.Host) || origin.User != nil ||
		origin.Path != "" || origin.RawQuery != "" || origin.Fragment != "" {
		return ErrIdentitySessionRefreshInvalid
	}
	fetchSite := request.Header.Values("Sec-Fetch-Site")
	if len(fetchSite) > 1 ||
		(len(fetchSite) == 1 && !strings.EqualFold(strings.TrimSpace(fetchSite[0]), "same-origin")) {
		return ErrIdentitySessionRefreshInvalid
	}
	return nil
}

func clearIdentitySessionCookies(writer http.ResponseWriter) {
	for _, name := range []string{IdentitySessionCookieName, IdentityRefreshCookieName} {
		http.SetCookie(writer, &http.Cookie{
			Name:     name,
			Path:     "/",
			Expires:  time.Unix(1, 0).UTC(),
			MaxAge:   -1,
			Secure:   true,
			HttpOnly: true,
			SameSite: http.SameSiteStrictMode,
		})
	}
}

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
	var bindingSession IdentityHTTPSession
	if purpose == IdentityVerificationBinding {
		if accountID == "" {
			writeError(writer, http.StatusBadRequest, "identity_registration_route_required", "new accounts must use the dedicated registration flow")
			return
		}
		if validateIdentityVerificationBindingBody(body, action) != nil {
			writeError(writer, http.StatusBadRequest, "identity_binding_request_invalid", "credential binding accepts only explicit public verification and trusted authorization identifiers")
			return
		}
		session, authenticated := server.resolveIdentityHTTPSession(writer, request, accountID)
		if !authenticated {
			return
		}
		if err := validateIdentitySessionRefreshBrowserRequest(request); err != nil {
			writeError(writer, http.StatusForbidden, "identity_binding_origin_rejected", "credential binding origin was rejected")
			return
		}
		actorID = session.ActorID
		bindingSession = session
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
		mutationTicketID := ""
		stepUpReceiptID := ""
		if purpose == IdentityVerificationBinding && accountID != "" {
			if server.identitySecurityTickets == nil {
				writeError(writer, http.StatusServiceUnavailable, "identity_binding_authority_unavailable", "credential binding authorization is not configured")
				return
			}
			mutationTicketID = stringValue(body, "mutation_ticket_id")
			stepUpReceiptID = stringValue(body, "step_up_receipt_id")
			if !validIdentitySecurityDigest(bindingSession.SessionDigest) ||
				!validIdentitySecurityDigest(mutationTicketID) ||
				!validIdentitySecurityDigest(stepUpReceiptID) {
				writeError(writer, http.StatusBadRequest, "identity_binding_authorization_required", "recent authentication, a mutation ticket, and a step-up receipt are required")
				return
			}
			ticket, err := server.identitySecurityTickets.ResolveIdentitySecurityMutationTicket(
				request.Context(), bindingSession.AccountID,
				mutationTicketID, stepUpReceiptID, "credential_bind",
			)
			if err != nil || ticket.AccountID != bindingSession.AccountID ||
				ticket.Operation != "credential_bind" ||
				ticket.TicketID != mutationTicketID ||
				ticket.ReceiptDigest != stepUpReceiptID {
				writeError(writer, http.StatusForbidden, "identity_binding_authorization_rejected", "credential binding could not be authorized")
				return
			}
			mutationTicketID = ticket.TicketID
			stepUpReceiptID = ticket.ReceiptDigest
		}
		completion := IdentityVerificationCompleteRequest{
			ChallengeID: stringValue(body, "challenge_id"), Code: stringValue(body, "code"),
			Channel: channel, Identifier: stringValue(body, "identifier"), Purpose: purpose,
			TenantID: stringValue(body, "tenant_id"), AccountID: accountID,
			ActorID: actorID, SessionDigest: bindingSession.SessionDigest,
			MutationTicketID: mutationTicketID, StepUpReceiptID: stepUpReceiptID,
			DisplayName: stringValue(body, "display_name"),
		}
		issueSession := purpose == IdentityVerificationRegistration ||
			purpose == IdentityVerificationLogin ||
			purpose == IdentityVerificationRecovery
		if issueSession {
			if server.identitySessionReceiptTransport == nil {
				writeError(writer, http.StatusServiceUnavailable, "identity_session_transport_unavailable", "identity session handoff is not configured")
				return
			}
			if err := server.identitySessionReceiptTransport.ValidateIdentitySessionRequest(request); err != nil {
				writeError(writer, http.StatusUpgradeRequired, "identity_session_secure_transport_required", "identity session handoff requires HTTPS")
				return
			}
		}
		var result IdentityVerificationResultDTO
		var receipt IdentitySessionIssuanceReceipt
		var err error
		if issueSession {
			result, receipt, err = server.identityVerification.CompleteAndIssueSession(request.Context(), completion)
		} else {
			result, err = server.identityVerification.Complete(request.Context(), completion)
		}
		if err != nil {
			writeIdentityVerificationHTTPError(writer, err)
			return
		}
		if issueSession {
			if err := server.identitySessionReceiptTransport.WriteIdentitySessionReceipt(writer, request, receipt); err != nil {
				writeError(writer, http.StatusInternalServerError, "identity_session_handoff_failed", "identity session handoff failed")
				return
			}
		}
		writeJSON(writer, http.StatusOK, publicIdentityVerificationResult(result))
	default:
		writeError(writer, http.StatusNotFound, "not_found", "route not found")
	}
}

func validateIdentityVerificationBindingBody(body JSONMap, action string) error {
	allowed := map[string]bool{
		"channel": true, "identifier": true, "purpose": true,
		"tenant_id": true, "account_id": true,
	}
	if action == "verify" {
		for _, key := range []string{
			"challenge_id", "code", "display_name",
			"mutation_ticket_id", "step_up_receipt_id",
		} {
			allowed[key] = true
		}
	}
	for key := range body {
		if !allowed[key] {
			return ErrIdentitySecurityRejected
		}
	}
	return nil
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
