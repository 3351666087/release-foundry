package releasefoundry

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/netip"
	"strings"
	"testing"
	"time"
)

type identityBrowserVerificationHarness struct {
	handler     http.Handler
	coordinator *httpSessionVerificationCoordinator
	store       *httpSessionVerificationStore
	vault       *httpSessionVerificationVault
	transport   *IdentitySessionCookieTransport
}

func newIdentityBrowserVerificationHarness(
	t *testing.T,
	now func() time.Time,
	trustedProxyCIDRs []netip.Prefix,
) identityBrowserVerificationHarness {
	t.Helper()
	store := &httpSessionVerificationStore{}
	vault := &httpSessionVerificationVault{}
	coordinator := &httpSessionVerificationCoordinator{now: now()}
	service, err := NewIdentityVerificationService(IdentityVerificationServiceOptions{
		Store:                  store,
		DeliveryVaultSealer:    vault,
		DeliveryVaultDeleter:   vault,
		DeliveryMode:           IdentityVerificationDeliveryTransactionalOutbox,
		TransactionCoordinator: coordinator,
		Now:                    now,
		DigestKey:              []byte("browser-verification-service-key-32"),
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(service.Close)
	policy, err := NewIdentityVerificationResponsePolicy(
		IdentityVerificationResponsePolicyOptions{
			Budget: DatabaseEnforcedIdentityVerificationAbuseBudget{},
			Now:    now,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	transport, err := NewIdentitySessionCookieTransport(
		IdentitySessionCookieTransportOptions{
			Now:               now,
			MaxLifetime:       30 * time.Minute,
			TrustedProxyCIDRs: trustedProxyCIDRs,
			IntentKey:         []byte("browser-verification-intent-key-32!"),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	handler := NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		IdentityVerification:               service,
		IdentityVerificationResponsePolicy: policy,
		IdentitySessionReceiptTransport:    transport,
		IdentityBrowserVerificationIntents: transport,
	})
	return identityBrowserVerificationHarness{
		handler:     handler,
		coordinator: coordinator,
		store:       store,
		vault:       vault,
		transport:   transport,
	}
}

func identityBrowserBeginRequest(path string, email string) *http.Request {
	request := httptest.NewRequest(
		http.MethodPost,
		"https://api.example.test"+path,
		strings.NewReader(fmt.Sprintf(`{"email":%q}`, email)),
	)
	request.Header.Set("Origin", "https://api.example.test")
	request.Header.Set("Sec-Fetch-Site", "same-origin")
	return request
}

func identityBrowserCompleteRequest(
	path string,
	challenge identityBrowserChallengeResponse,
	proof string,
	extra string,
	intentCookie *http.Cookie,
) *http.Request {
	request := httptest.NewRequest(
		http.MethodPost,
		"https://api.example.test"+path,
		strings.NewReader(fmt.Sprintf(
			`{"challenge_id":%q,"intent_id":%q,"proof":%q%s}`,
			challenge.ChallengeID,
			challenge.IntentID,
			proof,
			extra,
		)),
	)
	request.Header.Set("Origin", "https://api.example.test")
	request.Header.Set("Sec-Fetch-Site", "same-origin")
	if intentCookie != nil {
		request.AddCookie(intentCookie)
	}
	return request
}

func decodeIdentityBrowserChallenge(
	t *testing.T,
	response *httptest.ResponseRecorder,
) identityBrowserChallengeResponse {
	t.Helper()
	var challenge identityBrowserChallengeResponse
	if err := json.Unmarshal(response.Body.Bytes(), &challenge); err != nil {
		t.Fatalf("decode browser challenge: %v body=%s", err, response.Body.String())
	}
	return challenge
}

func TestIdentityBrowserRegistrationAndLoginIssueOpaqueChallengeAndRedirectSession(
	t *testing.T,
) {
	for _, testCase := range []struct {
		name         string
		beginPath    string
		completePath string
		purpose      IdentityVerificationPurpose
		email        string
		extra        string
	}{
		{
			name:         "registration",
			beginPath:    "/v1/identity/registration/email/begin",
			completePath: "/v1/identity/registration/email/complete",
			purpose:      IdentityVerificationRegistration,
			email:        "owner@qq.com",
			extra:        `,"display_name":"Browser Owner"`,
		},
		{
			name:         "login",
			beginPath:    "/v1/identity/login/email/begin",
			completePath: "/v1/identity/login/email/complete",
			purpose:      IdentityVerificationLogin,
			email:        "owner@foxmail.com",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			now := time.Date(2026, 7, 23, 2, 0, 0, 0, time.UTC)
			harness := newIdentityBrowserVerificationHarness(
				t,
				func() time.Time { return now },
				nil,
			)
			beginResponse := httptest.NewRecorder()
			harness.handler.ServeHTTP(
				beginResponse,
				identityBrowserBeginRequest(testCase.beginPath, testCase.email),
			)
			if beginResponse.Code != http.StatusAccepted {
				t.Fatalf(
					"begin status=%d body=%s",
					beginResponse.Code,
					beginResponse.Body.String(),
				)
			}
			challenge := decodeIdentityBrowserChallenge(t, beginResponse)
			if challenge.SchemaVersion != IdentityBrowserVerificationSchemaVersion ||
				challenge.ChallengeID == "" ||
				challenge.IntentID == "" ||
				!challenge.ExpiresAt.Equal(now.Add(10*time.Minute)) ||
				!challenge.ResendAfter.Equal(now.Add(time.Minute)) {
				t.Fatalf("unsafe or incomplete browser challenge: %#v", challenge)
			}
			if harness.store.createCalls != 1 ||
				harness.store.lastChallenge.ChallengeID != challenge.ChallengeID ||
				harness.store.lastChallenge.Purpose != testCase.purpose ||
				harness.store.lastChallenge.AccountID != "" ||
				harness.vault.sealRequest.Destination != testCase.email ||
				harness.vault.sealRequest.Code == "" {
				t.Fatalf(
					"begin did not issue the expected accountless challenge: store=%#v delivery=%v",
					harness.store,
					harness.vault.sealRequest,
				)
			}
			if beginResponse.Header().Get("Cache-Control") != "no-store" ||
				beginResponse.Header().Get("Pragma") != "no-cache" {
				t.Fatalf("begin omitted no-store headers: %#v", beginResponse.Header())
			}
			beginCookies := cookiesByName(beginResponse.Result().Cookies())
			intentCookie := beginCookies[IdentityBrowserVerificationIntentCookieName]
			if len(beginCookies) != 1 ||
				intentCookie == nil ||
				intentCookie.Path != "/" ||
				intentCookie.Domain != "" ||
				!intentCookie.Secure ||
				!intentCookie.HttpOnly ||
				intentCookie.SameSite != http.SameSiteStrictMode ||
				intentCookie.MaxAge != 10*60 ||
				!intentCookie.Expires.Equal(challenge.ExpiresAt) {
				t.Fatalf("unsafe browser intent cookie: %#v", intentCookie)
			}
			setCookie := beginResponse.Header().Get("Set-Cookie")
			for _, attribute := range []string{
				IdentityBrowserVerificationIntentCookieName + "=",
				"Path=/",
				"HttpOnly",
				"Secure",
				"SameSite=Strict",
			} {
				if !strings.Contains(setCookie, attribute) {
					t.Fatalf("intent cookie omitted %s: %s", attribute, setCookie)
				}
			}
			if strings.Contains(strings.ToLower(setCookie), "domain=") {
				t.Fatalf("intent cookie was not host-only: %s", setCookie)
			}
			for _, secret := range []string{
				testCase.email,
				harness.vault.sealRequest.Code,
				challenge.ChallengeID,
				challenge.IntentID,
			} {
				if strings.Contains(intentCookie.Value, secret) {
					t.Fatalf("encrypted intent cookie exposed private context %q", secret)
				}
			}
			if strings.Contains(beginResponse.Body.String(), testCase.email) ||
				strings.Contains(beginResponse.Body.String(), harness.vault.sealRequest.Code) {
				t.Fatalf("begin response leaked email or proof: %s", beginResponse.Body.String())
			}

			completeResponse := httptest.NewRecorder()
			harness.handler.ServeHTTP(
				completeResponse,
				identityBrowserCompleteRequest(
					testCase.completePath,
					challenge,
					harness.vault.sealRequest.Code,
					testCase.extra,
					intentCookie,
				),
			)
			if completeResponse.Code != http.StatusSeeOther ||
				completeResponse.Header().Get("Location") != "/console" ||
				completeResponse.Body.Len() != 0 ||
				completeResponse.Header().Get("Content-Type") != "" {
				t.Fatalf(
					"complete did not perform an empty console redirect: status=%d location=%q content_type=%q body=%q",
					completeResponse.Code,
					completeResponse.Header().Get("Location"),
					completeResponse.Header().Get("Content-Type"),
					completeResponse.Body.String(),
				)
			}
			if completeResponse.Header().Get("Cache-Control") != "no-store" ||
				completeResponse.Header().Get("Pragma") != "no-cache" {
				t.Fatalf("complete omitted no-store headers: %#v", completeResponse.Header())
			}
			if harness.coordinator.issueCalls != 1 ||
				harness.coordinator.completeCalls != 0 ||
				harness.coordinator.lastPurpose != testCase.purpose ||
				harness.coordinator.lastCommand.AccountID != "" ||
				harness.coordinator.lastCommand.TenantID != "tenant-http" {
				t.Fatalf(
					"complete did not use the accountless trusted session path: %#v",
					harness.coordinator,
				)
			}
			if testCase.purpose == IdentityVerificationRegistration &&
				harness.coordinator.lastCommand.DisplayName != "Browser Owner" {
				t.Fatalf(
					"registration display name was not propagated: %#v",
					harness.coordinator.lastCommand,
				)
			}
			completionCookies := cookiesByName(completeResponse.Result().Cookies())
			accessCookie := completionCookies[IdentitySessionCookieName]
			refreshCookie := completionCookies[IdentityRefreshCookieName]
			clearedIntent := completionCookies[IdentityBrowserVerificationIntentCookieName]
			if accessCookie == nil ||
				refreshCookie == nil ||
				clearedIntent == nil ||
				clearedIntent.MaxAge != -1 ||
				clearedIntent.Value != "" ||
				!clearedIntent.Secure ||
				!clearedIntent.HttpOnly ||
				clearedIntent.SameSite != http.SameSiteStrictMode {
				t.Fatalf("completion cookies were incomplete or unsafe: %#v", completionCookies)
			}
			for _, secret := range []string{
				testCase.email,
				harness.vault.sealRequest.Code,
				challenge.ChallengeID,
				challenge.IntentID,
				harness.coordinator.lastBearer,
				harness.coordinator.lastRefreshBearer,
			} {
				if strings.Contains(completeResponse.Body.String(), secret) ||
					strings.Contains(completeResponse.Header().Get("Location"), secret) {
					t.Fatalf("completion response leaked private material %q", secret)
				}
			}
			if _, _, err := harness.coordinator.lastReceipt.TakeBearerTokens(); err == nil {
				t.Fatal("session receipt bearer pair remained available after cookie handoff")
			}
		})
	}
}

func TestIdentityBrowserBeginReturnsSafeDecoyContextForInvalidEmail(t *testing.T) {
	now := time.Date(2026, 7, 23, 3, 0, 0, 0, time.UTC)
	harness := newIdentityBrowserVerificationHarness(
		t,
		func() time.Time { return now },
		nil,
	)
	response := httptest.NewRecorder()
	request := identityBrowserBeginRequest(
		"/v1/identity/login/email/begin",
		"not-an-email",
	)
	harness.handler.ServeHTTP(response, request)
	if response.Code != http.StatusAccepted {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	challenge := decodeIdentityBrowserChallenge(t, response)
	if challenge.ChallengeID == "" || challenge.IntentID == "" ||
		harness.store.createCalls != 0 {
		t.Fatalf(
			"invalid email did not receive a nonmutating opaque context: challenge=%#v creates=%d",
			challenge,
			harness.store.createCalls,
		)
	}
	intentCookie := cookiesByName(response.Result().Cookies())[IdentityBrowserVerificationIntentCookieName]
	if intentCookie == nil ||
		strings.Contains(response.Body.String(), "not-an-email") ||
		strings.Contains(intentCookie.Value, "not-an-email") {
		t.Fatalf("decoy response leaked invalid identifier: %s", response.Body.String())
	}
}

func TestIdentityBrowserBeginRejectsUnsafeRequestsBeforeChallengeCreation(t *testing.T) {
	now := time.Date(2026, 7, 23, 4, 0, 0, 0, time.UTC)
	testCases := []struct {
		name       string
		status     int
		mutate     func(*http.Request)
		requestURL string
		body       string
	}{
		{
			name:       "plaintext",
			status:     http.StatusUpgradeRequired,
			requestURL: "http://api.example.test/v1/identity/login/email/begin",
		},
		{
			name:   "missing origin",
			status: http.StatusForbidden,
			mutate: func(request *http.Request) { request.Header.Del("Origin") },
		},
		{
			name:   "multiple origin",
			status: http.StatusForbidden,
			mutate: func(request *http.Request) {
				request.Header.Add("Origin", "https://api.example.test")
			},
		},
		{
			name:   "cross origin",
			status: http.StatusForbidden,
			mutate: func(request *http.Request) {
				request.Header.Set("Origin", "https://attacker.example.test")
			},
		},
		{
			name:   "origin trailing slash",
			status: http.StatusForbidden,
			mutate: func(request *http.Request) {
				request.Header.Set("Origin", "https://api.example.test/")
			},
		},
		{
			name:   "origin port mismatch",
			status: http.StatusForbidden,
			mutate: func(request *http.Request) {
				request.Header.Set("Origin", "https://api.example.test:443")
			},
		},
		{
			name:   "cross site fetch",
			status: http.StatusForbidden,
			mutate: func(request *http.Request) {
				request.Header.Set("Sec-Fetch-Site", "cross-site")
			},
		},
		{
			name:   "ambiguous fetch metadata",
			status: http.StatusForbidden,
			mutate: func(request *http.Request) {
				request.Header.Add("Sec-Fetch-Site", "same-origin")
			},
		},
		{
			name:       "query injection",
			status:     http.StatusBadRequest,
			requestURL: "https://api.example.test/v1/identity/login/email/begin?purpose=registration",
		},
		{
			name:   "body key injection",
			status: http.StatusBadRequest,
			body:   `{"email":"owner@qq.com","tenant_id":"attacker"}`,
		},
	}
	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			harness := newIdentityBrowserVerificationHarness(
				t,
				func() time.Time { return now },
				nil,
			)
			requestURL := testCase.requestURL
			if requestURL == "" {
				requestURL = "https://api.example.test/v1/identity/login/email/begin"
			}
			body := testCase.body
			if body == "" {
				body = `{"email":"owner@qq.com"}`
			}
			request := httptest.NewRequest(
				http.MethodPost,
				requestURL,
				strings.NewReader(body),
			)
			request.Header.Set("Origin", "https://api.example.test")
			request.Header.Set("Sec-Fetch-Site", "same-origin")
			if testCase.mutate != nil {
				testCase.mutate(request)
			}
			response := httptest.NewRecorder()
			harness.handler.ServeHTTP(response, request)
			if response.Code != testCase.status {
				t.Fatalf(
					"status=%d want=%d body=%s",
					response.Code,
					testCase.status,
					response.Body.String(),
				)
			}
			if harness.store.createCalls != 0 {
				t.Fatalf("unsafe begin created a durable challenge: %#v", harness.store)
			}
			if response.Header().Get("Set-Cookie") != "" {
				t.Fatalf("unsafe begin emitted a cookie: %s", response.Header().Get("Set-Cookie"))
			}
		})
	}
}

func TestIdentityBrowserCompleteRejectsMismatchedIntentBeforeMutation(t *testing.T) {
	now := time.Date(2026, 7, 23, 5, 0, 0, 0, time.UTC)
	harness := newIdentityBrowserVerificationHarness(
		t,
		func() time.Time { return now },
		nil,
	)
	beginResponse := httptest.NewRecorder()
	harness.handler.ServeHTTP(
		beginResponse,
		identityBrowserBeginRequest(
			"/v1/identity/registration/email/begin",
			"owner@qq.com",
		),
	)
	if beginResponse.Code != http.StatusAccepted {
		t.Fatalf("begin status=%d body=%s", beginResponse.Code, beginResponse.Body.String())
	}
	challenge := decodeIdentityBrowserChallenge(t, beginResponse)
	intentCookie := cookiesByName(beginResponse.Result().Cookies())[IdentityBrowserVerificationIntentCookieName]
	if intentCookie == nil {
		t.Fatal("begin omitted intent cookie")
	}
	proof := harness.vault.sealRequest.Code

	type rejectedRequest struct {
		name   string
		status int
		build  func() *http.Request
	}
	base := func() *http.Request {
		return identityBrowserCompleteRequest(
			"/v1/identity/registration/email/complete",
			challenge,
			proof,
			`,"display_name":"Owner"`,
			intentCookie,
		)
	}
	testCases := []rejectedRequest{
		{
			name:   "missing cookie",
			status: http.StatusForbidden,
			build: func() *http.Request {
				return identityBrowserCompleteRequest(
					"/v1/identity/registration/email/complete",
					challenge,
					proof,
					`,"display_name":"Owner"`,
					nil,
				)
			},
		},
		{
			name:   "duplicate cookie",
			status: http.StatusForbidden,
			build: func() *http.Request {
				request := base()
				request.AddCookie(intentCookie)
				return request
			},
		},
		{
			name:   "tampered cookie",
			status: http.StatusForbidden,
			build: func() *http.Request {
				request := base()
				cookies := request.Cookies()
				request.Header.Del("Cookie")
				tampered := *cookies[0]
				replacement := byte('A')
				if tampered.Value[len(tampered.Value)-1] == replacement {
					replacement = 'B'
				}
				tampered.Value = tampered.Value[:len(tampered.Value)-1] +
					string(replacement)
				request.AddCookie(&tampered)
				return request
			},
		},
		{
			name:   "wrong challenge",
			status: http.StatusForbidden,
			build: func() *http.Request {
				changed := challenge
				changed.ChallengeID = "ivc_" + strings.Repeat("f", 36)
				return identityBrowserCompleteRequest(
					"/v1/identity/registration/email/complete",
					changed,
					proof,
					`,"display_name":"Owner"`,
					intentCookie,
				)
			},
		},
		{
			name:   "wrong intent id",
			status: http.StatusForbidden,
			build: func() *http.Request {
				changed := challenge
				changed.IntentID = "ivi_" + strings.Repeat("A", 32)
				return identityBrowserCompleteRequest(
					"/v1/identity/registration/email/complete",
					changed,
					proof,
					`,"display_name":"Owner"`,
					intentCookie,
				)
			},
		},
		{
			name:   "registration intent on login route",
			status: http.StatusForbidden,
			build: func() *http.Request {
				return identityBrowserCompleteRequest(
					"/v1/identity/login/email/complete",
					challenge,
					proof,
					"",
					intentCookie,
				)
			},
		},
		{
			name:   "cross origin",
			status: http.StatusForbidden,
			build: func() *http.Request {
				request := base()
				request.Header.Set("Origin", "https://attacker.example.test")
				return request
			},
		},
		{
			name:   "missing origin",
			status: http.StatusForbidden,
			build: func() *http.Request {
				request := base()
				request.Header.Del("Origin")
				return request
			},
		},
		{
			name:   "cross site fetch",
			status: http.StatusForbidden,
			build: func() *http.Request {
				request := base()
				request.Header.Set("Sec-Fetch-Site", "cross-site")
				return request
			},
		},
		{
			name:   "plaintext",
			status: http.StatusUpgradeRequired,
			build: func() *http.Request {
				request := base()
				request.URL.Scheme = "http"
				request.TLS = nil
				return request
			},
		},
		{
			name:   "query injection",
			status: http.StatusBadRequest,
			build: func() *http.Request {
				request := base()
				request.URL.RawQuery = "account_id=attacker"
				return request
			},
		},
		{
			name:   "body key injection",
			status: http.StatusBadRequest,
			build: func() *http.Request {
				request := identityBrowserCompleteRequest(
					"/v1/identity/registration/email/complete",
					challenge,
					proof,
					`,"display_name":"Owner","account_id":"attacker"`,
					intentCookie,
				)
				return request
			},
		},
	}
	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			response := httptest.NewRecorder()
			harness.handler.ServeHTTP(response, testCase.build())
			if response.Code != testCase.status {
				t.Fatalf(
					"status=%d want=%d body=%s",
					response.Code,
					testCase.status,
					response.Body.String(),
				)
			}
			if harness.coordinator.issueCalls != 0 ||
				harness.coordinator.completeCalls != 0 {
				t.Fatalf(
					"rejected completion reached durable mutation: %#v",
					harness.coordinator,
				)
			}
			if cookiesByName(response.Result().Cookies())[IdentitySessionCookieName] != nil ||
				cookiesByName(response.Result().Cookies())[IdentityRefreshCookieName] != nil {
				t.Fatalf("rejected completion emitted session cookies: %#v", response.Header())
			}
		})
	}

	success := httptest.NewRecorder()
	harness.handler.ServeHTTP(success, base())
	if success.Code != http.StatusSeeOther ||
		harness.coordinator.issueCalls != 1 {
		t.Fatalf(
			"valid completion failed after rejected probes: status=%d body=%s coordinator=%#v",
			success.Code,
			success.Body.String(),
			harness.coordinator,
		)
	}
	clearedIntent := cookiesByName(success.Result().Cookies())[IdentityBrowserVerificationIntentCookieName]
	replay := identityBrowserCompleteRequest(
		"/v1/identity/registration/email/complete",
		challenge,
		proof,
		`,"display_name":"Owner"`,
		clearedIntent,
	)
	replayResponse := httptest.NewRecorder()
	harness.handler.ServeHTTP(replayResponse, replay)
	if replayResponse.Code != http.StatusForbidden ||
		harness.coordinator.issueCalls != 1 {
		t.Fatalf(
			"cleared browser intent replay reached mutation: status=%d calls=%d body=%s",
			replayResponse.Code,
			harness.coordinator.issueCalls,
			replayResponse.Body.String(),
		)
	}
}

func TestIdentityBrowserExpiredIntentFailsBeforeMutation(t *testing.T) {
	current := time.Date(2026, 7, 23, 5, 30, 0, 0, time.UTC)
	harness := newIdentityBrowserVerificationHarness(
		t,
		func() time.Time { return current },
		nil,
	)
	email := "expiry@qq.com"
	beginResponse := httptest.NewRecorder()
	harness.handler.ServeHTTP(
		beginResponse,
		identityBrowserBeginRequest(
			"/v1/identity/registration/email/begin",
			email,
		),
	)
	if beginResponse.Code != http.StatusAccepted ||
		harness.store.createCalls != 1 {
		t.Fatalf(
			"begin failed: status=%d body=%s creates=%d",
			beginResponse.Code,
			beginResponse.Body.String(),
			harness.store.createCalls,
		)
	}
	challenge := decodeIdentityBrowserChallenge(t, beginResponse)
	intentCookie := cookiesByName(
		beginResponse.Result().Cookies(),
	)[IdentityBrowserVerificationIntentCookieName]
	if intentCookie == nil {
		t.Fatal("begin omitted intent cookie")
	}
	proof := harness.vault.sealRequest.Code

	current = challenge.ExpiresAt
	response := httptest.NewRecorder()
	harness.handler.ServeHTTP(
		response,
		identityBrowserCompleteRequest(
			"/v1/identity/registration/email/complete",
			challenge,
			proof,
			`,"display_name":"Expired Owner"`,
			intentCookie,
		),
	)
	if response.Code != http.StatusForbidden ||
		harness.coordinator.issueCalls != 0 ||
		harness.coordinator.completeCalls != 0 {
		t.Fatalf(
			"expired intent crossed the durable boundary: status=%d body=%s coordinator=%#v",
			response.Code,
			response.Body.String(),
			harness.coordinator,
		)
	}
	if cookiesByName(response.Result().Cookies())[IdentitySessionCookieName] != nil ||
		cookiesByName(response.Result().Cookies())[IdentityRefreshCookieName] != nil {
		t.Fatalf("expired intent emitted session cookies: %#v", response.Header())
	}
	for _, secret := range []string{
		email,
		proof,
		challenge.ChallengeID,
		challenge.IntentID,
		intentCookie.Value,
	} {
		if strings.Contains(response.Body.String(), secret) {
			t.Fatalf("expired-intent rejection leaked private context: %s", response.Body.String())
		}
	}
}

func TestIdentityBrowserVerificationTrustsForwardedHTTPSOnlyFromConfiguredProxy(
	t *testing.T,
) {
	now := time.Date(2026, 7, 23, 6, 0, 0, 0, time.UTC)
	harness := newIdentityBrowserVerificationHarness(
		t,
		func() time.Time { return now },
		[]netip.Prefix{netip.MustParsePrefix("10.0.0.0/8")},
	)
	spoofed := identityBrowserBeginRequest(
		"/v1/identity/login/email/begin",
		"owner@qq.com",
	)
	spoofed.URL.Scheme = "http"
	spoofed.TLS = nil
	spoofed.RemoteAddr = "203.0.113.8:44000"
	spoofed.Header.Set("X-Forwarded-Proto", "https")
	spoofedResponse := httptest.NewRecorder()
	harness.handler.ServeHTTP(spoofedResponse, spoofed)
	if spoofedResponse.Code != http.StatusUpgradeRequired ||
		harness.store.createCalls != 0 {
		t.Fatalf(
			"untrusted proxy spoof was accepted: status=%d creates=%d",
			spoofedResponse.Code,
			harness.store.createCalls,
		)
	}

	trusted := identityBrowserBeginRequest(
		"/v1/identity/login/email/begin",
		"owner@qq.com",
	)
	trusted.URL.Scheme = "http"
	trusted.TLS = nil
	trusted.RemoteAddr = "10.24.8.3:44000"
	trusted.Header.Set("X-Forwarded-Proto", "https")
	trustedResponse := httptest.NewRecorder()
	harness.handler.ServeHTTP(trustedResponse, trusted)
	if trustedResponse.Code != http.StatusAccepted ||
		harness.store.createCalls != 1 {
		t.Fatalf(
			"trusted HTTPS proxy was rejected: status=%d body=%s creates=%d",
			trustedResponse.Code,
			trustedResponse.Body.String(),
			harness.store.createCalls,
		)
	}
}

func TestIdentityBrowserIntentConfigurationAndFormattingFailClosed(t *testing.T) {
	if _, err := NewIdentitySessionCookieTransport(IdentitySessionCookieTransportOptions{
		IntentKey: []byte("too-short"),
	}); err == nil {
		t.Fatal("short browser intent key was accepted")
	}
	if _, err := NewIdentitySessionCookieTransport(IdentitySessionCookieTransportOptions{
		IntentKey:         []byte("browser-verification-intent-key-32!"),
		IntentMaxLifetime: 31 * time.Minute,
	}); err == nil {
		t.Fatal("oversized browser intent lifetime was accepted")
	}
	email := "private@qq.com"
	issue := IdentityBrowserVerificationIntentIssue{
		ChallengeID: "ivc_" + strings.Repeat("a", 36),
		Purpose:     IdentityVerificationRegistration,
		TenantID:    "tenant-http",
		ProjectID:   "project-http",
		Identifier:  email,
		ExpiresAt:   time.Date(2026, 7, 23, 7, 10, 0, 0, time.UTC),
	}
	claim := IdentityBrowserVerificationIntentClaim{Identifier: email}
	for _, rendered := range []string{
		fmt.Sprint(issue),
		fmt.Sprintf("%#v", issue),
		fmt.Sprint(claim),
		fmt.Sprintf("%#v", claim),
	} {
		if strings.Contains(rendered, email) {
			t.Fatalf("browser intent formatting leaked email: %s", rendered)
		}
	}
}
