package ashrclone

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync"
	"testing"
	"time"
)

type identityDeliveryCapture struct {
	mu         sync.Mutex
	deliveries []IdentityChallengeDelivery
}

func (capture *identityDeliveryCapture) DeliverIdentityChallenge(value IdentityChallengeDelivery) error {
	capture.mu.Lock()
	defer capture.mu.Unlock()
	capture.deliveries = append(capture.deliveries, value)
	return nil
}

func (capture *identityDeliveryCapture) last(t *testing.T) IdentityChallengeDelivery {
	t.Helper()
	capture.mu.Lock()
	defer capture.mu.Unlock()
	if len(capture.deliveries) == 0 {
		t.Fatal("expected identity challenge delivery")
	}
	return capture.deliveries[len(capture.deliveries)-1]
}

type identityAuditCapture struct {
	mu     sync.Mutex
	events []IdentityAuditEvent
}

func (capture *identityAuditCapture) RecordIdentityAudit(value IdentityAuditEvent) {
	capture.mu.Lock()
	defer capture.mu.Unlock()
	capture.events = append(capture.events, value)
}

type denyIdentityRateLimiter struct{}

func (denyIdentityRateLimiter) AllowIdentityAttempt(string, string) bool { return false }

func newIdentityHTTPTestServer(t *testing.T, identity *IdentityService, delivery IdentityChallengeDeliverer, audit IdentityAuditSink, limiter IdentityRateLimiter) *httptest.Server {
	t.Helper()
	return newIdentityHTTPTestServerWithOAuth(t, identity, delivery, audit, limiter, nil)
}

func newIdentityHTTPTestServerWithOAuth(
	t *testing.T,
	identity *IdentityService,
	delivery IdentityChallengeDeliverer,
	audit IdentityAuditSink,
	limiter IdentityRateLimiter,
	oauth *OAuthFlowCoordinator,
) *httptest.Server {
	t.Helper()
	return httptest.NewServer(NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		BackendName:         "memory_service_v0",
		BackendReady:        true,
		IdentityService:     identity,
		IdentityDelivery:    delivery,
		IdentityAudit:       audit,
		IdentityRateLimiter: limiter,
		OAuthCoordinator:    oauth,
	}))
}

func identityJSONRequest(t *testing.T, method, url string, body any, headers map[string]string) (*http.Response, []byte) {
	t.Helper()
	var reader io.Reader
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			t.Fatal(err)
		}
		reader = bytes.NewReader(encoded)
	}
	request, err := http.NewRequest(method, url, reader)
	if err != nil {
		t.Fatal(err)
	}
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	for key, value := range headers {
		request.Header.Set(key, value)
	}
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	payload, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatal(err)
	}
	return response, payload
}

func registerThroughIdentityHTTP(t *testing.T, serverURL string, delivery *identityDeliveryCapture, email string) A3IdentityView {
	t.Helper()
	response, payload := identityJSONRequest(t, http.MethodPost, serverURL+"/v1/identity/registration/email/begin", JSONMap{"email": email}, nil)
	if response.StatusCode != http.StatusAccepted {
		t.Fatalf("registration begin status %d: %s", response.StatusCode, payload)
	}
	if strings.Contains(string(payload), email) || strings.Contains(string(payload), delivery.last(t).Secret) {
		t.Fatalf("registration begin leaked target or proof: %s", payload)
	}
	delivered := delivery.last(t)
	response, payload = identityJSONRequest(t, http.MethodPost, serverURL+"/v1/identity/registration/email/complete", JSONMap{
		"challenge_id": delivered.ChallengeID,
		"proof":        delivered.Secret,
		"display_name": "Owner",
	}, nil)
	if response.StatusCode != http.StatusCreated {
		t.Fatalf("registration complete status %d: %s", response.StatusCode, payload)
	}
	var envelope struct {
		Identity A3IdentityView `json:"identity"`
	}
	if err := json.Unmarshal(payload, &envelope); err != nil {
		t.Fatal(err)
	}
	if envelope.Identity.PrimaryEmailHint == email || envelope.Identity.AccountID == "" {
		t.Fatalf("unsafe registration identity view: %s", payload)
	}
	return envelope.Identity
}

func loginThroughIdentityHTTP(t *testing.T, serverURL string, delivery *identityDeliveryCapture, email string) identityAuthCompletion {
	t.Helper()
	response, payload := identityJSONRequest(t, http.MethodPost, serverURL+"/v1/identity/login/email/begin", JSONMap{"email": email}, nil)
	if response.StatusCode != http.StatusAccepted {
		t.Fatalf("login begin status %d: %s", response.StatusCode, payload)
	}
	delivered := delivery.last(t)
	response, payload = identityJSONRequest(t, http.MethodPost, serverURL+"/v1/identity/login/email/complete", JSONMap{
		"challenge_id": delivered.ChallengeID,
		"proof":        delivered.Secret,
	}, nil)
	if response.StatusCode != http.StatusOK {
		t.Fatalf("login complete status %d: %s", response.StatusCode, payload)
	}
	if response.Header.Get("Cache-Control") != "no-store" {
		t.Fatalf("auth completion must be non-cacheable: %#v", response.Header)
	}
	var auth identityAuthCompletion
	if err := json.Unmarshal(payload, &auth); err != nil {
		t.Fatal(err)
	}
	if auth.SessionID == "" || auth.SessionToken == "" || strings.Count(string(payload), auth.SessionToken) != 1 {
		t.Fatalf("session credential was not emitted exactly once: %s", payload)
	}
	return auth
}

func identityAuthHeaders(auth identityAuthCompletion) map[string]string {
	return map[string]string{
		"Authorization":     "Bearer " + auth.SessionToken,
		"X-Ashr-Session-ID": auth.SessionID,
	}
}

func TestIdentityHTTPRegistrationLoginMeAndRevokeAreSafe(t *testing.T) {
	identity := NewIdentityService()
	delivery := &identityDeliveryCapture{}
	audit := &identityAuditCapture{}
	server := newIdentityHTTPTestServer(t, identity, delivery, audit, nil)
	defer server.Close()

	view := registerThroughIdentityHTTP(t, server.URL, delivery, "owner@163.com")
	auth := loginThroughIdentityHTTP(t, server.URL, delivery, "owner@163.com")
	if auth.AccountID != view.AccountID {
		t.Fatalf("login account mismatch: %+v %+v", auth, view)
	}

	response, payload := identityJSONRequest(t, http.MethodGet, server.URL+"/v1/me", nil, identityAuthHeaders(auth))
	if response.StatusCode != http.StatusOK {
		t.Fatalf("/v1/me status %d: %s", response.StatusCode, payload)
	}
	for _, forbidden := range []string{"owner@163.com", auth.SessionToken, "provider_subject", "verified_email"} {
		if strings.Contains(string(payload), forbidden) {
			t.Fatalf("/v1/me leaked %q: %s", forbidden, payload)
		}
	}

	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/sessions/revoke", JSONMap{}, identityAuthHeaders(auth))
	if response.StatusCode != http.StatusOK {
		t.Fatalf("revoke status %d: %s", response.StatusCode, payload)
	}
	response, _ = identityJSONRequest(t, http.MethodGet, server.URL+"/v1/me", nil, identityAuthHeaders(auth))
	if response.StatusCode != http.StatusUnauthorized {
		t.Fatalf("revoked session unexpectedly authorized: %d", response.StatusCode)
	}

	audit.mu.Lock()
	defer audit.mu.Unlock()
	if len(audit.events) < 5 {
		t.Fatalf("expected safe audit events, got %+v", audit.events)
	}
	encoded, _ := json.Marshal(audit.events)
	if strings.Contains(string(encoded), auth.SessionToken) || strings.Contains(string(encoded), "owner@163.com") {
		t.Fatalf("audit events leaked credentials or email: %s", encoded)
	}
}

func TestIdentityHTTPUnknownLoginUsesGenericCompletionError(t *testing.T) {
	identity := NewIdentityService()
	delivery := &identityDeliveryCapture{}
	server := newIdentityHTTPTestServer(t, identity, delivery, nil, nil)
	defer server.Close()

	response, knownShape := identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/login/email/begin", JSONMap{"email": "unknown@qq.com"}, nil)
	if response.StatusCode != http.StatusAccepted {
		t.Fatalf("unknown login begin status %d: %s", response.StatusCode, knownShape)
	}
	delivered := delivery.last(t)
	response, payload := identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/login/email/complete", JSONMap{
		"challenge_id": delivered.ChallengeID,
		"proof":        delivered.Secret,
	}, nil)
	if response.StatusCode != http.StatusUnauthorized || !strings.Contains(string(payload), `"code":"invalid_credentials"`) {
		t.Fatalf("unknown login exposed a non-generic error: %d %s", response.StatusCode, payload)
	}
	if identity.AccountCount() != 0 {
		t.Fatal("unknown HTTP login created an account")
	}
}

func TestIdentityHTTPOpaqueBindingTicketRequiresConsentAndFreshSession(t *testing.T) {
	now := time.Date(2026, 7, 14, 0, 0, 0, 0, time.UTC)
	identity := NewIdentityServiceWithClock(func() time.Time { return now })
	delivery := &identityDeliveryCapture{}
	server := newIdentityHTTPTestServer(t, identity, delivery, nil, nil)
	defer server.Close()

	view := registerThroughIdentityHTTP(t, server.URL, delivery, "owner@qq.com")
	auth := loginThroughIdentityHTTP(t, server.URL, delivery, "owner@qq.com")
	ticket, err := identity.IssueCredentialBindingTicket(view.AccountID, BindCredentialRequest{
		Provider:        "wechat_open",
		ProviderSubject: "wechat-private-subject",
		ProviderUnionID: "wechat-private-union",
		VerifiedEmail:   "owner@qq.com",
	})
	if err != nil {
		t.Fatalf("issue trusted binding ticket: %v", err)
	}

	response, payload := identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/credentials/bind", JSONMap{
		"binding_ticket_id":    ticket.TicketID,
		"binding_ticket_proof": ticket.Secret,
		"explicit_consent":     false,
	}, identityAuthHeaders(auth))
	if response.StatusCode != http.StatusForbidden {
		t.Fatalf("binding without consent status %d: %s", response.StatusCode, payload)
	}

	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/credentials/bind", JSONMap{
		"binding_ticket_id":    ticket.TicketID,
		"binding_ticket_proof": ticket.Secret,
		"explicit_consent":     true,
	}, identityAuthHeaders(auth))
	if response.StatusCode != http.StatusOK {
		t.Fatalf("binding status %d: %s", response.StatusCode, payload)
	}
	for _, forbidden := range []string{"wechat-private-subject", "wechat-private-union", "owner@qq.com", ticket.Secret} {
		if strings.Contains(string(payload), forbidden) {
			t.Fatalf("binding response leaked %q: %s", forbidden, payload)
		}
	}

	now = now.Add(11 * time.Minute)
	staleTicket, err := identity.IssueCredentialBindingTicket(view.AccountID, BindCredentialRequest{
		Provider:        "qq",
		ProviderSubject: "qq-private-subject",
	})
	if err != nil {
		t.Fatalf("issue stale-session ticket: %v", err)
	}
	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/credentials/bind", JSONMap{
		"binding_ticket_id":    staleTicket.TicketID,
		"binding_ticket_proof": staleTicket.Secret,
		"explicit_consent":     true,
	}, identityAuthHeaders(auth))
	if response.StatusCode != http.StatusUnauthorized || !strings.Contains(string(payload), "recent_reauthentication_required") {
		t.Fatalf("stale session was accepted for binding: %d %s", response.StatusCode, payload)
	}
}

func TestIdentityHTTPMFADeliveryNeverLeaksProof(t *testing.T) {
	identity := NewIdentityService()
	delivery := &identityDeliveryCapture{}
	server := newIdentityHTTPTestServer(t, identity, delivery, nil, nil)
	defer server.Close()

	view := registerThroughIdentityHTTP(t, server.URL, delivery, "owner@foxmail.com")
	if _, err := identity.EnableTwoFactor(view.AccountID, []string{"totp"}); err != nil {
		t.Fatal(err)
	}
	response, payload := identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/login/email/begin", JSONMap{"email": "owner@foxmail.com"}, nil)
	if response.StatusCode != http.StatusAccepted {
		t.Fatalf("login begin: %d %s", response.StatusCode, payload)
	}
	firstFactor := delivery.last(t)
	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/login/email/complete", JSONMap{
		"challenge_id": firstFactor.ChallengeID,
		"proof":        firstFactor.Secret,
	}, nil)
	if response.StatusCode != http.StatusAccepted {
		t.Fatalf("MFA required response: %d %s", response.StatusCode, payload)
	}
	mfa := delivery.last(t)
	if mfa.Purpose != "mfa" || strings.Contains(string(payload), mfa.Secret) || strings.Contains(string(payload), "owner@foxmail.com") {
		t.Fatalf("MFA response leaked proof or target: %s", payload)
	}
	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/mfa/complete", JSONMap{
		"challenge_id": mfa.ChallengeID,
		"proof":        mfa.Secret,
	}, nil)
	if response.StatusCode != http.StatusOK {
		t.Fatalf("MFA completion: %d %s", response.StatusCode, payload)
	}
}

func TestIdentityHTTPStrictJSONMethodsLimitsRateAndDeliveryFailClosed(t *testing.T) {
	identity := NewIdentityService()
	delivery := &identityDeliveryCapture{}
	server := newIdentityHTTPTestServer(t, identity, delivery, nil, nil)
	defer server.Close()

	response, payload := identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/registration/email/begin", JSONMap{
		"email":      "owner@163.com",
		"unexpected": true,
	}, nil)
	if response.StatusCode != http.StatusBadRequest || !strings.Contains(string(payload), "invalid_json") {
		t.Fatalf("unknown field was accepted: %d %s", response.StatusCode, payload)
	}
	response, _ = identityJSONRequest(t, http.MethodGet, server.URL+"/v1/identity/registration/email/begin", nil, nil)
	if response.StatusCode != http.StatusMethodNotAllowed || response.Header.Get("Allow") != http.MethodPost {
		t.Fatalf("wrong method response: %d %#v", response.StatusCode, response.Header)
	}
	large := strings.Repeat("a", identityRequestBodyLimit+1)
	response, _ = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/registration/email/begin", JSONMap{"email": large + "@163.com"}, nil)
	if response.StatusCode != http.StatusBadRequest {
		t.Fatalf("oversized body status = %d", response.StatusCode)
	}

	rateLimited := newIdentityHTTPTestServer(t, NewIdentityService(), delivery, nil, denyIdentityRateLimiter{})
	defer rateLimited.Close()
	response, _ = identityJSONRequest(t, http.MethodPost, rateLimited.URL+"/v1/identity/login/email/begin", JSONMap{"email": "owner@qq.com"}, nil)
	if response.StatusCode != http.StatusTooManyRequests {
		t.Fatalf("rate limiter status = %d", response.StatusCode)
	}

	unconfigured := httptest.NewServer(NewHTTPServer(NewMemoryService()))
	defer unconfigured.Close()
	response, payload = identityJSONRequest(t, http.MethodPost, unconfigured.URL+"/v1/identity/registration/email/begin", JSONMap{"email": "owner@163.com"}, nil)
	if response.StatusCode != http.StatusServiceUnavailable || !strings.Contains(string(payload), "identity_service_unavailable") {
		t.Fatalf("missing delivery adapter did not fail closed: %d %s", response.StatusCode, payload)
	}
}

func TestIdentityHTTPOAuthRegistrationAndLoginPreserveIntentAndSafeClaims(t *testing.T) {
	now := time.Date(2026, 7, 14, 0, 0, 0, 0, time.UTC)
	identity := NewIdentityServiceWithClock(func() time.Time { return now })
	delivery := &identityDeliveryCapture{}
	audit := &identityAuditCapture{}
	adapter := &oauthAdapterStub{identity: OAuthProviderIdentity{
		Provider:        "qq",
		ProviderSubject: "qq-private-registration-subject",
		ProviderUnionID: "qq-private-union",
		VerifiedEmail:   "new-owner@qq.com",
		VerifiedPhone:   "+8613800000000",
	}}
	coordinator := newOAuthCoordinatorForTest(
		t,
		func() time.Time { return now },
		identity,
		map[string]OAuthProviderAdapter{"qq": adapter},
		map[string][]string{"qq": {"https://console.ashr.example/oauth/callback"}},
	)
	server := newIdentityHTTPTestServerWithOAuth(t, identity, delivery, audit, nil, coordinator)
	defer server.Close()

	response, payload := identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/begin", JSONMap{
		"provider":     "qq",
		"intent":       "registration",
		"redirect_uri": "https://console.ashr.example/oauth/callback",
	}, nil)
	if response.StatusCode != http.StatusAccepted || response.Header.Get("Cache-Control") != "no-store" {
		t.Fatalf("OAuth registration begin: %d %s %#v", response.StatusCode, payload, response.Header)
	}
	var begin OAuthBeginResult
	if err := json.Unmarshal(payload, &begin); err != nil {
		t.Fatal(err)
	}
	if begin.Intent != OAuthIntentRegistration || begin.Provider != "qq" || begin.FlowID == "" {
		t.Fatalf("registration intent was not preserved: %s", payload)
	}
	if !strings.HasPrefix(begin.AuthorizationURL, "https://provider.example/authorize?") ||
		!strings.Contains(begin.AuthorizationURL, url.QueryEscape(adapter.authorizationRequest.State)) {
		t.Fatalf("authorization URL was redacted or omitted: %s", payload)
	}

	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/complete", JSONMap{
		"flow_id":      begin.FlowID,
		"state":        adapter.authorizationRequest.State,
		"code":         "private-registration-code",
		"display_name": "QQ Owner",
	}, nil)
	if response.StatusCode != http.StatusCreated {
		t.Fatalf("OAuth registration complete: %d %s", response.StatusCode, payload)
	}
	for _, forbidden := range []string{
		"qq-private-registration-subject",
		"qq-private-union",
		"new-owner@qq.com",
		"+8613800000000",
		"private-registration-code",
	} {
		if strings.Contains(string(payload), forbidden) {
			t.Fatalf("OAuth registration leaked %q: %s", forbidden, payload)
		}
	}
	var registered struct {
		Identity A3IdentityView `json:"identity"`
	}
	if err := json.Unmarshal(payload, &registered); err != nil {
		t.Fatal(err)
	}
	if registered.Identity.AccountID == "" ||
		registered.Identity.Locale != "zh-CN" ||
		registered.Identity.Region != "cn" {
		t.Fatalf("domestic canonical account defaults missing: %s", payload)
	}
	if identity.AccountCount() != 1 {
		t.Fatalf("registration intent should create exactly one account, got %d", identity.AccountCount())
	}

	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/begin", JSONMap{
		"provider":     "qq",
		"intent":       "login",
		"redirect_uri": "https://console.ashr.example/oauth/callback",
	}, nil)
	if response.StatusCode != http.StatusAccepted {
		t.Fatalf("OAuth login begin: %d %s", response.StatusCode, payload)
	}
	if err := json.Unmarshal(payload, &begin); err != nil {
		t.Fatal(err)
	}
	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/complete", JSONMap{
		"flow_id": begin.FlowID,
		"state":   adapter.authorizationRequest.State,
		"code":    "private-login-code",
	}, nil)
	if response.StatusCode != http.StatusOK || response.Header.Get("Cache-Control") != "no-store" {
		t.Fatalf("OAuth login complete: %d %s %#v", response.StatusCode, payload, response.Header)
	}
	var auth identityAuthCompletion
	if err := json.Unmarshal(payload, &auth); err != nil {
		t.Fatal(err)
	}
	if auth.AccountID != registered.Identity.AccountID ||
		auth.SessionToken == "" ||
		strings.Count(string(payload), auth.SessionToken) != 1 {
		t.Fatalf("OAuth session credential not delivered exactly once: %s", payload)
	}
	if identity.AccountCount() != 1 {
		t.Fatal("OAuth login intent unexpectedly registered an account")
	}
}

func TestIdentityHTTPOAuthLoginNeverAutoLinksMatchingEmailAndMFAIsDelivered(t *testing.T) {
	identity := NewIdentityService()
	delivery := &identityDeliveryCapture{}
	existing := registerIdentityAccount(t, identity, "existing@163.com")
	adapter := &oauthAdapterStub{identity: OAuthProviderIdentity{
		Provider:        "wechat_open",
		ProviderSubject: "unknown-wechat-subject",
		VerifiedEmail:   existing.PrimaryEmail,
	}}
	coordinator := newOAuthCoordinatorForTest(
		t,
		time.Now,
		identity,
		map[string]OAuthProviderAdapter{"wechat_open": adapter},
		map[string][]string{"wechat_open": {"https://console.ashr.example/oauth/callback"}},
	)
	server := newIdentityHTTPTestServerWithOAuth(t, identity, delivery, nil, nil, coordinator)
	defer server.Close()

	response, payload := identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/begin", JSONMap{
		"provider":     "wechat_open",
		"intent":       "login",
		"redirect_uri": "https://console.ashr.example/oauth/callback",
	}, nil)
	if response.StatusCode != http.StatusAccepted {
		t.Fatalf("unknown OAuth login begin: %d %s", response.StatusCode, payload)
	}
	var begin OAuthBeginResult
	if err := json.Unmarshal(payload, &begin); err != nil {
		t.Fatal(err)
	}
	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/complete", JSONMap{
		"flow_id": begin.FlowID,
		"state":   adapter.authorizationRequest.State,
		"code":    "unknown-login-code",
	}, nil)
	if response.StatusCode != http.StatusUnauthorized ||
		!strings.Contains(string(payload), `"code":"invalid_credentials"`) {
		t.Fatalf("unknown OAuth login was not generic: %d %s", response.StatusCode, payload)
	}
	if identity.AccountCount() != 1 {
		t.Fatal("matching verified email created or merged a canonical account")
	}
	view, err := identity.A3View(existing.AccountID)
	if err != nil {
		t.Fatal(err)
	}
	if len(view.Credentials) != 1 || view.Credentials[0].Provider != "email_magic_link" {
		t.Fatalf("matching verified email auto-linked OAuth credential: %+v", view.Credentials)
	}

	ticket, err := identity.IssueCredentialBindingTicket(existing.AccountID, BindCredentialRequest{
		Provider:        "wechat_open",
		ProviderSubject: "bound-wechat-subject",
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := identity.BindCredentialWithTicket(existing.AccountID, existing.AccountID, ticket.TicketID, ticket.Secret, true, true); err != nil {
		t.Fatal(err)
	}
	if _, err := identity.EnableTwoFactor(existing.AccountID, []string{"totp"}); err != nil {
		t.Fatal(err)
	}
	adapter.identity = OAuthProviderIdentity{
		Provider:        "wechat_open",
		ProviderSubject: "bound-wechat-subject",
	}
	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/begin", JSONMap{
		"provider":     "wechat_open",
		"intent":       "login",
		"redirect_uri": "https://console.ashr.example/oauth/callback",
	}, nil)
	if response.StatusCode != http.StatusAccepted {
		t.Fatalf("bound OAuth login begin: %d %s", response.StatusCode, payload)
	}
	if err := json.Unmarshal(payload, &begin); err != nil {
		t.Fatal(err)
	}
	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/complete", JSONMap{
		"flow_id": begin.FlowID,
		"state":   adapter.authorizationRequest.State,
		"code":    "mfa-login-code",
	}, nil)
	if response.StatusCode != http.StatusAccepted || !strings.Contains(string(payload), `"status":"mfa_required"`) {
		t.Fatalf("OAuth MFA response: %d %s", response.StatusCode, payload)
	}
	mfa := delivery.last(t)
	if mfa.Purpose != "mfa" ||
		strings.Contains(string(payload), mfa.Secret) ||
		strings.Contains(string(payload), existing.PrimaryEmail) {
		t.Fatalf("OAuth MFA leaked delivery proof/target: %s", payload)
	}
}

func TestIdentityHTTPOAuthLinkRequiresFreshSessionAndEmitsOpaqueTicketOnce(t *testing.T) {
	now := time.Date(2026, 7, 14, 0, 0, 0, 0, time.UTC)
	identity := NewIdentityServiceWithClock(func() time.Time { return now })
	delivery := &identityDeliveryCapture{}
	view := registerIdentityAccount(t, identity, "link-owner@qq.com")
	login, err := identity.BeginEmailLogin(view.PrimaryEmail)
	if err != nil {
		t.Fatal(err)
	}
	authResult, err := identity.CompleteEmailLogin(login.ChallengeID, login.Secret)
	if err != nil {
		t.Fatal(err)
	}
	auth := identityAuthCompletion{
		AccountID:    authResult.AccountID,
		SessionID:    authResult.SessionID,
		SessionToken: authResult.SessionToken,
	}
	adapter := &oauthAdapterStub{identity: OAuthProviderIdentity{
		Provider:        "wechat_open",
		ProviderSubject: "wechat-link-private-subject",
		ProviderUnionID: "wechat-link-private-union",
		VerifiedEmail:   view.PrimaryEmail,
	}}
	coordinator := newOAuthCoordinatorForTest(
		t,
		func() time.Time { return now },
		identity,
		map[string]OAuthProviderAdapter{"wechat_open": adapter},
		map[string][]string{"wechat_open": {"https://console.ashr.example/oauth/callback"}},
	)
	server := newIdentityHTTPTestServerWithOAuth(t, identity, delivery, nil, nil, coordinator)
	defer server.Close()

	beginBody := JSONMap{
		"provider":     "wechat_open",
		"intent":       "link",
		"redirect_uri": "https://console.ashr.example/oauth/callback",
	}
	response, payload := identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/begin", beginBody, nil)
	if response.StatusCode != http.StatusUnauthorized {
		t.Fatalf("unauthenticated OAuth link begin: %d %s", response.StatusCode, payload)
	}
	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/begin", beginBody, identityAuthHeaders(auth))
	if response.StatusCode != http.StatusAccepted {
		t.Fatalf("OAuth link begin: %d %s", response.StatusCode, payload)
	}
	var begin OAuthBeginResult
	if err := json.Unmarshal(payload, &begin); err != nil {
		t.Fatal(err)
	}
	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/complete", JSONMap{
		"flow_id": begin.FlowID,
		"state":   adapter.authorizationRequest.State,
		"code":    "private-link-code",
	}, nil)
	if response.StatusCode != http.StatusOK || response.Header.Get("Cache-Control") != "no-store" {
		t.Fatalf("OAuth link complete: %d %s %#v", response.StatusCode, payload, response.Header)
	}
	var ticket identityOAuthLinkCompletion
	if err := json.Unmarshal(payload, &ticket); err != nil {
		t.Fatal(err)
	}
	if ticket.BindingTicketID == "" ||
		ticket.BindingTicketProof == "" ||
		strings.Count(string(payload), ticket.BindingTicketProof) != 1 {
		t.Fatalf("binding ticket proof was not emitted exactly once: %s", payload)
	}
	for _, forbidden := range []string{
		"wechat-link-private-subject",
		"wechat-link-private-union",
		view.PrimaryEmail,
		"private-link-code",
	} {
		if strings.Contains(string(payload), forbidden) {
			t.Fatalf("OAuth link response leaked %q: %s", forbidden, payload)
		}
	}

	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/credentials/bind", JSONMap{
		"binding_ticket_id":    ticket.BindingTicketID,
		"binding_ticket_proof": ticket.BindingTicketProof,
		"explicit_consent":     true,
	}, identityAuthHeaders(auth))
	if response.StatusCode != http.StatusOK {
		t.Fatalf("bind OAuth ticket: %d %s", response.StatusCode, payload)
	}
	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/complete", JSONMap{
		"flow_id": begin.FlowID,
		"state":   adapter.authorizationRequest.State,
		"code":    "private-link-code",
	}, nil)
	if response.StatusCode != http.StatusUnauthorized ||
		!strings.Contains(string(payload), string(OAuthInvalidOrExpiredFlow)) {
		t.Fatalf("OAuth callback replay accepted: %d %s", response.StatusCode, payload)
	}
}

func TestIdentityHTTPOAuthFailsClosedAndStrictlyValidatesRequests(t *testing.T) {
	server := newIdentityHTTPTestServer(t, NewIdentityService(), &identityDeliveryCapture{}, nil, nil)
	defer server.Close()
	response, payload := identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/begin", JSONMap{
		"provider":     "qq",
		"intent":       "login",
		"redirect_uri": "https://console.ashr.example/oauth/callback",
	}, nil)
	if response.StatusCode != http.StatusServiceUnavailable ||
		!strings.Contains(string(payload), string(OAuthProviderUnavailable)) {
		t.Fatalf("missing OAuth coordinator did not fail closed: %d %s", response.StatusCode, payload)
	}

	identity := NewIdentityService()
	adapter := &oauthAdapterStub{exchangeErr: errors.New("access_token=provider-secret")}
	coordinator := newOAuthCoordinatorForTest(
		t,
		time.Now,
		identity,
		map[string]OAuthProviderAdapter{"qq": adapter},
		map[string][]string{"qq": {"https://console.ashr.example/oauth/callback"}},
	)
	configured := newIdentityHTTPTestServerWithOAuth(t, identity, &identityDeliveryCapture{}, nil, nil, coordinator)
	defer configured.Close()
	response, payload = identityJSONRequest(t, http.MethodPost, configured.URL+"/v1/identity/oauth/begin", JSONMap{
		"provider":     "qq",
		"intent":       "login",
		"redirect_uri": "https://attacker.example/callback",
	}, nil)
	if response.StatusCode != http.StatusBadRequest ||
		!strings.Contains(string(payload), string(OAuthRedirectNotAllowed)) {
		t.Fatalf("unlisted redirect accepted: %d %s", response.StatusCode, payload)
	}
	response, payload = identityJSONRequest(t, http.MethodPost, configured.URL+"/v1/identity/oauth/begin", JSONMap{
		"provider":     "qq",
		"intent":       "login",
		"redirect_uri": "https://console.ashr.example/oauth/callback",
		"account_id":   "attacker-selected-account",
	}, nil)
	if response.StatusCode != http.StatusBadRequest || !strings.Contains(string(payload), "invalid_json") {
		t.Fatalf("OAuth begin accepted unknown/account-selection field: %d %s", response.StatusCode, payload)
	}
	large := strings.Repeat("a", identityRequestBodyLimit+1)
	response, payload = identityJSONRequest(t, http.MethodPost, configured.URL+"/v1/identity/oauth/begin", JSONMap{
		"provider":     "qq",
		"intent":       "login",
		"redirect_uri": "https://console.ashr.example/oauth/callback?padding=" + large,
	}, nil)
	if response.StatusCode != http.StatusBadRequest || !strings.Contains(string(payload), "invalid_json") {
		t.Fatalf("oversized OAuth request accepted: %d %s", response.StatusCode, payload)
	}
	response, payload = identityJSONRequest(t, http.MethodPost, configured.URL+"/v1/identity/oauth/begin", JSONMap{
		"provider":     "qq",
		"intent":       "login",
		"redirect_uri": "https://console.ashr.example/oauth/callback",
	}, nil)
	if response.StatusCode != http.StatusAccepted {
		t.Fatalf("OAuth exchange-failure begin: %d %s", response.StatusCode, payload)
	}
	var begin OAuthBeginResult
	if err := json.Unmarshal(payload, &begin); err != nil {
		t.Fatal(err)
	}
	response, payload = identityJSONRequest(t, http.MethodPost, configured.URL+"/v1/identity/oauth/complete", JSONMap{
		"flow_id": begin.FlowID,
		"state":   adapter.authorizationRequest.State,
		"code":    "provider-code",
	}, nil)
	if response.StatusCode != http.StatusServiceUnavailable ||
		!strings.Contains(string(payload), string(OAuthExchangeFailed)) ||
		strings.Contains(string(payload), "provider-secret") ||
		strings.Contains(string(payload), "access_token") {
		t.Fatalf("provider exchange error was not sanitized: %d %s", response.StatusCode, payload)
	}
}

func TestIdentityHTTPOAuthWrongStateDoesNotConsumeFlowAndMetadataIsIntentScoped(t *testing.T) {
	identity := NewIdentityService()
	adapter := &oauthAdapterStub{identity: OAuthProviderIdentity{
		Provider:        "qq",
		ProviderSubject: "unknown-login-subject",
	}}
	coordinator := newOAuthCoordinatorForTest(
		t,
		time.Now,
		identity,
		map[string]OAuthProviderAdapter{"qq": adapter},
		map[string][]string{"qq": {"https://console.ashr.example/oauth/callback"}},
	)
	server := newIdentityHTTPTestServerWithOAuth(t, identity, &identityDeliveryCapture{}, nil, nil, coordinator)
	defer server.Close()

	response, payload := identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/begin", JSONMap{
		"provider":     "qq",
		"intent":       "login",
		"redirect_uri": "https://console.ashr.example/oauth/callback",
	}, nil)
	if response.StatusCode != http.StatusAccepted {
		t.Fatalf("begin OAuth login: %d %s", response.StatusCode, payload)
	}
	var begin OAuthBeginResult
	if err := json.Unmarshal(payload, &begin); err != nil {
		t.Fatal(err)
	}
	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/complete", JSONMap{
		"flow_id": begin.FlowID,
		"state":   "attacker-state",
		"code":    "attacker-code",
	}, nil)
	if response.StatusCode != http.StatusUnauthorized ||
		!strings.Contains(string(payload), string(OAuthInvalidOrExpiredFlow)) {
		t.Fatalf("wrong OAuth state accepted: %d %s", response.StatusCode, payload)
	}
	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/complete", JSONMap{
		"flow_id": begin.FlowID,
		"state":   adapter.authorizationRequest.State,
		"code":    "legitimate-code",
	}, nil)
	if response.StatusCode != http.StatusUnauthorized ||
		!strings.Contains(string(payload), `"code":"invalid_credentials"`) {
		t.Fatalf("legitimate state was consumed by mismatch: %d %s", response.StatusCode, payload)
	}

	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/begin", JSONMap{
		"provider":     "qq",
		"intent":       "login",
		"redirect_uri": "https://console.ashr.example/oauth/callback",
	}, nil)
	if response.StatusCode != http.StatusAccepted {
		t.Fatalf("second OAuth begin: %d %s", response.StatusCode, payload)
	}
	if err := json.Unmarshal(payload, &begin); err != nil {
		t.Fatal(err)
	}
	response, payload = identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/complete", JSONMap{
		"flow_id":      begin.FlowID,
		"state":        adapter.authorizationRequest.State,
		"code":         "legitimate-code",
		"display_name": "must-not-apply-to-login",
	}, nil)
	if response.StatusCode != http.StatusBadRequest ||
		!strings.Contains(string(payload), string(OAuthInvalidRequest)) {
		t.Fatalf("login accepted registration-only metadata: %d %s", response.StatusCode, payload)
	}
}

func TestIdentityHTTPOAuthCoordinatorIdentityMismatchFailsClosed(t *testing.T) {
	httpIdentity := NewIdentityService()
	coordinatorIdentity := NewIdentityService()
	adapter := &oauthAdapterStub{}
	coordinator := newOAuthCoordinatorForTest(
		t,
		time.Now,
		coordinatorIdentity,
		map[string]OAuthProviderAdapter{"qq": adapter},
		map[string][]string{"qq": {"https://console.ashr.example/oauth/callback"}},
	)
	server := newIdentityHTTPTestServerWithOAuth(
		t,
		httpIdentity,
		&identityDeliveryCapture{},
		nil,
		nil,
		coordinator,
	)
	defer server.Close()

	response, payload := identityJSONRequest(t, http.MethodPost, server.URL+"/v1/identity/oauth/begin", JSONMap{
		"provider":     "qq",
		"intent":       "login",
		"redirect_uri": "https://console.ashr.example/oauth/callback",
	}, nil)
	if response.StatusCode != http.StatusServiceUnavailable ||
		!strings.Contains(string(payload), string(OAuthProviderUnavailable)) {
		t.Fatalf("mismatched OAuth identity authority did not fail closed: %d %s", response.StatusCode, payload)
	}
}

func TestIdentityProviderManifestRetainsDomesticOAuthCapabilities(t *testing.T) {
	view := registerIdentityAccount(t, NewIdentityService(), "owner@qq.com")
	_ = view
	capabilities := IdentityProviderCapabilities()
	seen := map[string]IdentityProviderCapability{}
	for _, capability := range capabilities {
		seen[capability.Provider] = capability
	}
	for _, provider := range []string{"qq", "wechat_open"} {
		capability, ok := seen[provider]
		if !ok ||
			!capability.Enabled ||
			capability.Region != "cn" ||
			!capability.SupportsRegistration ||
			!capability.SupportsLogin ||
			!capability.SupportsExplicitBinding ||
			!capability.PKCERequired {
			t.Fatalf("domestic OAuth capability missing or unsafe for %s: %+v", provider, capability)
		}
	}
}
