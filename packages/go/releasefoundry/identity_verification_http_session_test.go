package releasefoundry

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/netip"
	"strings"
	"testing"
	"time"
)

type httpSessionVerificationStore struct{}

func (*httpSessionVerificationStore) CreateIdentityVerificationChallenge(
	context.Context,
	IdentityVerificationChallenge,
	time.Duration,
) error {
	return nil
}

func (*httpSessionVerificationStore) ConsumeIdentityVerificationChallenge(
	context.Context,
	string,
	func(IdentityVerificationChallenge) error,
) (IdentityVerificationChallenge, error) {
	return IdentityVerificationChallenge{}, nil
}

func (*httpSessionVerificationStore) IsProductionIdentityVerificationStore() {}

func (*httpSessionVerificationStore) UsesTransactionalIdentityVerificationOutbox() {}

func (*httpSessionVerificationStore) IdentityVerificationDeliveryScope() (string, string) {
	return "tenant-http", "project-http"
}

func (*httpSessionVerificationStore) CreateIdentityVerificationChallengeWithDelivery(
	context.Context,
	IdentityVerificationChallenge,
	time.Duration,
	string,
	string,
) error {
	return nil
}

type httpSessionVerificationVault struct{}

func (*httpSessionVerificationVault) SealIdentityDelivery(
	context.Context,
	IdentityDeliverySealRequest,
) (string, error) {
	return "identity_delivery_vault_ref_http_test", nil
}

func (*httpSessionVerificationVault) DeleteIdentityDelivery(context.Context, string) error {
	return nil
}

type httpSessionVerificationCoordinator struct {
	now               time.Time
	completeCalls     int
	issueCalls        int
	lastPurpose       IdentityVerificationPurpose
	lastCommand       IdentityVerificationCompletionCommand
	lastReceipt       IdentitySessionIssuanceReceipt
	lastBearer        string
	lastRefreshBearer string
}

func (coordinator *httpSessionVerificationCoordinator) CompleteIdentityVerification(
	_ context.Context,
	command IdentityVerificationCompletionCommand,
) (IdentityVerificationResultDTO, error) {
	coordinator.completeCalls++
	coordinator.lastPurpose = command.Purpose
	coordinator.lastCommand = command
	return httpSessionVerificationResult(command, coordinator.now), nil
}

func (coordinator *httpSessionVerificationCoordinator) CompleteIdentityVerificationAndIssueSession(
	_ context.Context,
	command IdentityVerificationCompletionCommand,
) (IdentityVerificationResultDTO, IdentitySessionIssuanceReceipt, error) {
	coordinator.issueCalls++
	coordinator.lastPurpose = command.Purpose
	coordinator.lastBearer = "releasefoundry_session.v2." + strings.Repeat("A", 43)
	coordinator.lastRefreshBearer = "releasefoundry_refresh.v2." + strings.Repeat("B", 43)
	coordinator.lastReceipt = newIdentitySessionIssuanceReceiptWithRefresh(
		"session-http-test",
		"v2",
		"v2",
		coordinator.now.Add(24*time.Hour),
		coordinator.now.Add(30*24*time.Hour),
		coordinator.lastBearer,
		coordinator.lastRefreshBearer,
	)
	return httpSessionVerificationResult(command, coordinator.now), coordinator.lastReceipt, nil
}

func (*httpSessionVerificationCoordinator) IsProductionIdentityVerificationTransactionCoordinator() {}

func httpSessionVerificationResult(
	command IdentityVerificationCompletionCommand,
	now time.Time,
) IdentityVerificationResultDTO {
	accountID := command.AccountID
	if accountID == "" {
		accountID = "account-http-test"
	}
	credential := IdentityCredentialDTO{
		SchemaVersion: UnifiedIdentitySchemaVersion,
		CredentialID:  "credential-http-test",
		Kind:          command.CredentialKind,
		Provider:      IdentityProviderLocal,
		Verified:      true,
		CanLogin:      true,
		LinkedAt:      now,
	}
	return IdentityVerificationResultDTO{
		SchemaVersion: IdentityVerificationSchemaVersion,
		ChallengeID:   command.ChallengeID,
		Channel:       command.Channel,
		Purpose:       command.Purpose,
		TenantID:      command.TenantID,
		Account: IdentityAccountDTO{
			SchemaVersion:   UnifiedIdentitySchemaVersion,
			AccountID:       accountID,
			PrimaryID:       accountID,
			Status:          "active",
			Credentials:     []IdentityCredentialDTO{credential},
			CredentialCount: 1,
			CreatedAt:       now,
			UpdatedAt:       now,
		},
		Credential: credential,
		VerifiedAt: now,
	}
}

func newHTTPSessionVerificationHandler(
	t *testing.T,
	now time.Time,
	transport IdentitySessionReceiptTransport,
) (http.Handler, *httpSessionVerificationCoordinator) {
	t.Helper()
	coordinator := &httpSessionVerificationCoordinator{now: now}
	vault := &httpSessionVerificationVault{}
	service, err := NewIdentityVerificationService(IdentityVerificationServiceOptions{
		Store:                  &httpSessionVerificationStore{},
		DeliveryVaultSealer:    vault,
		DeliveryVaultDeleter:   vault,
		DeliveryMode:           IdentityVerificationDeliveryTransactionalOutbox,
		TransactionCoordinator: coordinator,
		Now:                    func() time.Time { return now },
		DigestKey:              []byte("http-session-verification-key-32-bytes"),
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(service.Close)
	return NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		IdentityVerification:            service,
		IdentitySessionReceiptTransport: transport,
	}), coordinator
}

func identitySessionVerifyRequest(purpose IdentityVerificationPurpose, secure bool) *http.Request {
	scheme := "http"
	if secure {
		scheme = "https"
	}
	accountField := ""
	if purpose != IdentityVerificationBinding {
		accountField = `,"account_id":"account-http-test"`
	}
	body := fmt.Sprintf(
		`{"challenge_id":"challenge-http-test","code":"123456","channel":"email","identifier":"person@example.test","purpose":%q,"tenant_id":"tenant-http"%s}`,
		purpose,
		accountField,
	)
	return httptest.NewRequest(
		http.MethodPost,
		scheme+"://api.example.test/v1/identity-verification/verify",
		strings.NewReader(body),
	)
}

func TestIdentityVerificationHTTPLoginAndRecoveryUseOneTimeSecureCookieOnly(t *testing.T) {
	now := time.Date(2026, 7, 11, 12, 0, 0, 0, time.UTC)
	for _, purpose := range []IdentityVerificationPurpose{
		IdentityVerificationLogin,
		IdentityVerificationRecovery,
	} {
		t.Run(string(purpose), func(t *testing.T) {
			transport, err := NewIdentitySessionCookieTransport(IdentitySessionCookieTransportOptions{
				Now:         func() time.Time { return now },
				MaxLifetime: 30 * time.Minute,
			})
			if err != nil {
				t.Fatal(err)
			}
			handler, coordinator := newHTTPSessionVerificationHandler(t, now, transport)
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, identitySessionVerifyRequest(purpose, true))

			if response.Code != http.StatusOK {
				t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
			}
			if coordinator.issueCalls != 1 || coordinator.completeCalls != 0 || coordinator.lastPurpose != purpose {
				t.Fatalf("unexpected completion path: %#v", coordinator)
			}
			cookies := response.Result().Cookies()
			if len(cookies) != 2 {
				t.Fatalf("cookies=%#v", cookies)
			}
			cookiesByName := map[string]*http.Cookie{}
			for _, cookie := range cookies {
				cookiesByName[cookie.Name] = cookie
			}
			accessCookie := cookiesByName[IdentitySessionCookieName]
			refreshCookie := cookiesByName[IdentityRefreshCookieName]
			if accessCookie == nil || accessCookie.Value != coordinator.lastBearer ||
				accessCookie.Path != "/" || accessCookie.Domain != "" ||
				!accessCookie.Secure || !accessCookie.HttpOnly ||
				accessCookie.SameSite != http.SameSiteStrictMode || accessCookie.MaxAge != 1800 ||
				!accessCookie.Expires.Equal(now.Add(30*time.Minute)) {
				t.Fatalf("unsafe access session cookie: %#v", accessCookie)
			}
			if refreshCookie == nil || refreshCookie.Value != coordinator.lastRefreshBearer ||
				refreshCookie.Path != "/" || refreshCookie.Domain != "" ||
				!refreshCookie.Secure || !refreshCookie.HttpOnly ||
				refreshCookie.SameSite != http.SameSiteStrictMode ||
				refreshCookie.MaxAge != 30*24*60*60 ||
				!refreshCookie.Expires.Equal(now.Add(30*24*time.Hour)) {
				t.Fatalf("unsafe refresh session cookie: %#v", refreshCookie)
			}
			setCookies := response.Header().Values("Set-Cookie")
			if len(setCookies) != 2 {
				t.Fatalf("set-cookie headers=%#v", setCookies)
			}
			for _, setCookie := range setCookies {
				for _, attribute := range []string{"Path=/", "HttpOnly", "Secure", "SameSite=Strict"} {
					if !strings.Contains(setCookie, attribute) {
						t.Fatalf("session cookie omitted %s: %s", attribute, setCookie)
					}
				}
			}
			for _, secret := range []string{
				coordinator.lastBearer,
				coordinator.lastRefreshBearer,
				"session-http-test",
				"v2",
			} {
				if strings.Contains(response.Body.String(), secret) {
					t.Fatalf("public response leaked session material: %s", response.Body.String())
				}
			}
			if _, _, err := coordinator.lastReceipt.TakeBearerTokens(); err == nil {
				t.Fatal("receipt bearer pair remained available after cookie handoff")
			}
		})
	}
}

func TestIdentityVerificationHTTPFailsBeforeMutationWithoutTrustedTransport(t *testing.T) {
	now := time.Date(2026, 7, 11, 13, 0, 0, 0, time.UTC)
	handler, coordinator := newHTTPSessionVerificationHandler(t, now, nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, identitySessionVerifyRequest(IdentityVerificationLogin, true))
	if response.Code != http.StatusServiceUnavailable ||
		!strings.Contains(response.Body.String(), `"identity_session_transport_unavailable"`) {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	if coordinator.issueCalls != 0 || coordinator.completeCalls != 0 {
		t.Fatalf("missing transport mutated identity state: %#v", coordinator)
	}
	if response.Header().Get("Set-Cookie") != "" {
		t.Fatal("missing transport emitted a cookie")
	}
}

func TestIdentityVerificationHTTPTrustsForwardedHTTPSOnlyFromConfiguredProxy(t *testing.T) {
	now := time.Date(2026, 7, 11, 14, 0, 0, 0, time.UTC)
	transport, err := NewIdentitySessionCookieTransport(IdentitySessionCookieTransportOptions{
		Now:               func() time.Time { return now },
		TrustedProxyCIDRs: []netip.Prefix{netip.MustParsePrefix("10.0.0.0/8")},
	})
	if err != nil {
		t.Fatal(err)
	}
	handler, coordinator := newHTTPSessionVerificationHandler(t, now, transport)

	spoofed := identitySessionVerifyRequest(IdentityVerificationLogin, false)
	spoofed.RemoteAddr = "203.0.113.9:43120"
	spoofed.Header.Set("X-Forwarded-Proto", "https")
	spoofedResponse := httptest.NewRecorder()
	handler.ServeHTTP(spoofedResponse, spoofed)
	if spoofedResponse.Code != http.StatusUpgradeRequired || coordinator.issueCalls != 0 {
		t.Fatalf("untrusted proxy header was accepted: status=%d calls=%d", spoofedResponse.Code, coordinator.issueCalls)
	}

	proxied := identitySessionVerifyRequest(IdentityVerificationRecovery, false)
	proxied.RemoteAddr = "10.24.8.3:43120"
	proxied.Header.Set("X-Forwarded-Proto", "https")
	proxiedResponse := httptest.NewRecorder()
	handler.ServeHTTP(proxiedResponse, proxied)
	if proxiedResponse.Code != http.StatusOK || coordinator.issueCalls != 1 {
		t.Fatalf("trusted HTTPS proxy was rejected: status=%d body=%s", proxiedResponse.Code, proxiedResponse.Body.String())
	}
}

func TestIdentityVerificationHTTPRejectsAccountlessBindingOutsideRegistrationRoute(t *testing.T) {
	now := time.Date(2026, 7, 11, 15, 0, 0, 0, time.UTC)
	handler, coordinator := newHTTPSessionVerificationHandler(t, now, nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, identitySessionVerifyRequest(IdentityVerificationBinding, false))
	if response.Code != http.StatusBadRequest ||
		!strings.Contains(response.Body.String(), `"code":"identity_registration_route_required"`) {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	if coordinator.completeCalls != 0 || coordinator.issueCalls != 0 {
		t.Fatalf("accountless binding reached the verification coordinator: %#v", coordinator)
	}
	if response.Header().Get("Set-Cookie") != "" {
		t.Fatal("rejected accountless binding emitted a session cookie")
	}
}

func TestIdentityVerificationHTTPExistingAccountBindingRequiresTrustedAuthorization(t *testing.T) {
	now := time.Date(2026, 7, 14, 10, 0, 0, 0, time.UTC)
	baseHandler, coordinator := newHTTPSessionVerificationHandler(t, now, nil)
	server := baseHandler.(*HTTPServer)
	accountID := "11111111-1111-4111-8111-111111111111"
	sessionDigest := strings.Repeat("a", 64)
	ticketID := strings.Repeat("b", 64)
	stepUpID := strings.Repeat("c", 64)
	server.identitySessions = identityHTTPTestSessionResolver{session: IdentityHTTPSession{
		AccountID: accountID, ActorID: accountID, SessionID: "session-binding",
		SessionDigest: sessionDigest,
	}}
	server.identitySecurityTickets = identitySecurityTestResolver{ticket: IdentitySecurityMutationTicket{
		TicketID: ticketID, AccountID: accountID, Operation: "credential_bind",
		ReceiptDigest: stepUpID, ExpiresAt: now.Add(time.Minute),
	}}

	requestBody := func(extra string) string {
		return fmt.Sprintf(
			`{"challenge_id":"challenge-http-test","code":"123456","channel":"email","identifier":"person@example.test","purpose":"binding","tenant_id":"tenant-http","account_id":%q%s}`,
			accountID, extra,
		)
	}
	request := func(body string, origin string) *http.Request {
		result := httptest.NewRequest(
			http.MethodPost,
			"https://api.example.test/v1/identity-verification/verify",
			strings.NewReader(body),
		)
		result.Header.Set("Origin", origin)
		result.Header.Set("Sec-Fetch-Site", "same-origin")
		return result
	}

	missing := httptest.NewRecorder()
	server.ServeHTTP(missing, request(requestBody(""), "https://api.example.test"))
	if missing.Code != http.StatusBadRequest || coordinator.completeCalls != 0 {
		t.Fatalf("missing trusted binding authority was accepted: status=%d body=%s", missing.Code, missing.Body.String())
	}

	crossOrigin := httptest.NewRecorder()
	server.ServeHTTP(crossOrigin, request(requestBody(
		fmt.Sprintf(`,"mutation_ticket_id":%q,"step_up_receipt_id":%q`, ticketID, stepUpID),
	), "https://evil.example.test"))
	if crossOrigin.Code != http.StatusForbidden || coordinator.completeCalls != 0 {
		t.Fatalf("cross-origin binding was accepted: status=%d body=%s", crossOrigin.Code, crossOrigin.Body.String())
	}

	untrustedBody := httptest.NewRecorder()
	server.ServeHTTP(untrustedBody, request(requestBody(
		fmt.Sprintf(`,"mutation_ticket_id":%q,"step_up_receipt_id":%q,"actor_id":%q`, ticketID, stepUpID, accountID),
	), "https://api.example.test"))
	if untrustedBody.Code != http.StatusBadRequest || coordinator.completeCalls != 0 {
		t.Fatalf("body authority was accepted: status=%d body=%s", untrustedBody.Code, untrustedBody.Body.String())
	}

	success := httptest.NewRecorder()
	server.ServeHTTP(success, request(requestBody(
		fmt.Sprintf(`,"mutation_ticket_id":%q,"step_up_receipt_id":%q`, ticketID, stepUpID),
	), "https://api.example.test"))
	if success.Code != http.StatusOK || coordinator.completeCalls != 1 {
		t.Fatalf("authorized binding failed: status=%d body=%s", success.Code, success.Body.String())
	}
	for _, secret := range []string{"123456", "person@example.test", ticketID, stepUpID, sessionDigest} {
		if strings.Contains(success.Body.String(), secret) {
			t.Fatalf("authorized binding response leaked private input %q: %s", secret, success.Body.String())
		}
	}
	command := coordinator.lastCommand
	if command.AccountID != accountID || command.ActorID != accountID ||
		command.SessionDigest != sessionDigest ||
		command.MutationTicketID != ticketID ||
		command.StepUpReceiptID != stepUpID {
		t.Fatalf("trusted binding authority was not propagated: %#v", command)
	}
}

func TestIdentitySessionCookieTransportConsumesReceiptExactlyOnce(t *testing.T) {
	now := time.Date(2026, 7, 11, 16, 0, 0, 0, time.UTC)
	transport, err := NewIdentitySessionCookieTransport(IdentitySessionCookieTransportOptions{
		Now:         func() time.Time { return now },
		MaxLifetime: time.Hour,
	})
	if err != nil {
		t.Fatal(err)
	}
	receipt := newIdentitySessionIssuanceReceiptWithRefresh(
		"session-once",
		"v3",
		"v3",
		now.Add(2*time.Hour),
		now.Add(60*24*time.Hour),
		"releasefoundry_session.v3."+strings.Repeat("B", 43),
		"releasefoundry_refresh.v3."+strings.Repeat("C", 43),
	)
	if bearer, err := receipt.TakeBearerToken(); !errors.Is(err, ErrIdentitySessionBearerPairRequired) || bearer != "" {
		t.Fatalf("paired receipt allowed access-only transfer: nonempty=%t err=%v", bearer != "", err)
	}
	if bearer, err := receipt.TakeRefreshToken(); !errors.Is(err, ErrIdentitySessionBearerPairRequired) || bearer != "" {
		t.Fatalf("paired receipt allowed refresh-only transfer: nonempty=%t err=%v", bearer != "", err)
	}
	request := httptest.NewRequest(http.MethodPost, "https://api.example.test/verify", nil)
	first := httptest.NewRecorder()
	if err := transport.WriteIdentitySessionReceipt(first, request, receipt); err != nil {
		t.Fatal(err)
	}
	second := httptest.NewRecorder()
	if err := transport.WriteIdentitySessionReceipt(second, request, receipt); err == nil {
		t.Fatal("receipt was accepted twice")
	}
	if second.Header().Get("Set-Cookie") != "" {
		t.Fatal("second receipt handoff emitted a cookie")
	}
}
