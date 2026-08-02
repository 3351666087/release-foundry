package releasefoundry

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

type identitySecurityTestResolver struct {
	ticket IdentitySecurityMutationTicket
	err    error
}

func (r identitySecurityTestResolver) ResolveIdentitySecurityMutationTicket(context.Context, string, string, string, string) (IdentitySecurityMutationTicket, error) {
	return r.ticket, r.err
}

type identitySecurityTestStore struct {
	mutation IdentitySecurityMutation
	result   IdentitySecurityHTTPMutationResultDTO
	err      error
}

func (s *identitySecurityTestStore) GetIdentitySecurityPosture(context.Context, string) (IdentitySecurityHTTPPostureDTO, error) {
	return IdentitySecurityHTTPPostureDTO{
		PasswordStatus: "absent", TwoFactorStatus: "disabled",
		TwoFactorOptional: true, TwoFactorRecommended: true,
	}, s.err
}

func (s *identitySecurityTestStore) MutateIdentitySecurity(_ context.Context, mutation IdentitySecurityMutation) (IdentitySecurityHTTPMutationResultDTO, error) {
	s.mutation = mutation
	return s.result, s.err
}

func identitySecurityTestHandler(accountID string, resolver IdentitySecurityTicketResolver, store IdentitySecurityHTTPStore) http.Handler {
	return NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		IdentitySessions:        identityHTTPTestSessionResolver{session: IdentityHTTPSession{AccountID: accountID, ActorID: accountID, SessionID: "session"}},
		IdentitySecurityTickets: resolver,
		IdentitySecurity:        store,
	})
}

func TestIdentitySecurityHTTPRejectsPublicSecretMaterial(t *testing.T) {
	store := &identitySecurityTestStore{}
	handler := identitySecurityTestHandler("account", identitySecurityTestResolver{}, store)
	for _, field := range []string{"password", "totp_code", "secret_ref", "recovery_codes", "secret_digest", "actor_id"} {
		body := `{"mutation_ticket_id":"ticket","step_up_receipt_id":"step","idempotency_key":"idem-key","` + field + `":"private"}`
		req := httptest.NewRequest(http.MethodPost, "/v1/accounts/account/password/enroll", strings.NewReader(body))
		req.Header.Set("Idempotency-Key", "idem-key")
		res := httptest.NewRecorder()
		handler.ServeHTTP(res, req)
		if res.Code != http.StatusBadRequest || !strings.Contains(res.Body.String(), "secret_input_rejected") {
			t.Fatalf("field %s was not rejected: %d %s", field, res.Code, res.Body.String())
		}
	}
	if store.mutation.Operation != "" {
		t.Fatal("rejected public secret reached security store")
	}
}

func TestIdentitySecurityHTTPRejectsTrailingSecretObject(t *testing.T) {
	store := &identitySecurityTestStore{}
	handler := identitySecurityTestHandler("account", identitySecurityTestResolver{}, store)
	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/accounts/account/password/enroll",
		strings.NewReader(
			`{"mutation_ticket_id":"ticket","step_up_receipt_id":"step","idempotency_key":"idem-key"}`+
				"\n"+`{"password":"plaintext-secret"}`,
		),
	)
	req.Header.Set("Idempotency-Key", "idem-key")
	res := httptest.NewRecorder()
	handler.ServeHTTP(res, req)
	if res.Code != http.StatusBadRequest || !strings.Contains(res.Body.String(), "invalid_json") {
		t.Fatalf("trailing JSON object was not rejected: %d %s", res.Code, res.Body.String())
	}
	if store.mutation.Operation != "" {
		t.Fatal("trailing secret object reached security store")
	}
}

func TestIdentitySecurityHTTPRequiresBoundTicketAndIdempotency(t *testing.T) {
	store := &identitySecurityTestStore{result: IdentitySecurityHTTPMutationResultDTO{PasswordStatus: "set", SessionsRevoked: 1}}
	ticket := IdentitySecurityMutationTicket{TicketID: "ticket", AccountID: "account", Operation: "password_enroll", ExpiresAt: time.Now().Add(time.Minute)}
	body := `{"mutation_ticket_id":"ticket","step_up_receipt_id":"step","idempotency_key":"idem-key"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/accounts/account/password/enroll", strings.NewReader(body))
	req.Header.Set("Idempotency-Key", "idem-key")
	res := httptest.NewRecorder()
	identitySecurityTestHandler("account", identitySecurityTestResolver{ticket: ticket}, store).ServeHTTP(res, req)
	if res.Code != http.StatusOK || !strings.Contains(res.Body.String(), IdentitySecurityHTTPSchemaVersion) {
		t.Fatalf("mutation failed: %d %s", res.Code, res.Body.String())
	}
	if store.mutation.AccountID != "account" || store.mutation.ActorID != "account" || store.mutation.Operation != "password_enroll" || store.mutation.IdempotencyKey != "idem-key" {
		t.Fatalf("trusted mutation lost binding: %#v", store.mutation)
	}

	for name, resolver := range map[string]IdentitySecurityTicketResolver{
		"wrong account":   identitySecurityTestResolver{ticket: IdentitySecurityMutationTicket{AccountID: "other", Operation: "password_enroll", ExpiresAt: time.Now().Add(time.Minute)}},
		"wrong operation": identitySecurityTestResolver{ticket: IdentitySecurityMutationTicket{AccountID: "account", Operation: "password_change", ExpiresAt: time.Now().Add(time.Minute)}},
		"resolver error":  identitySecurityTestResolver{err: errors.New("private lookup failure")},
	} {
		t.Run(name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, "/v1/accounts/account/password/enroll", strings.NewReader(body))
			req.Header.Set("Idempotency-Key", "idem-key")
			res := httptest.NewRecorder()
			identitySecurityTestHandler("account", resolver, &identitySecurityTestStore{}).ServeHTTP(res, req)
			if res.Code != http.StatusForbidden || strings.Contains(res.Body.String(), "private lookup") {
				t.Fatalf("unsafe rejection: %d %s", res.Code, res.Body.String())
			}
		})
	}
}

func TestIdentitySecurityHTTPDistinguishesUnavailableFromRejected(t *testing.T) {
	ticket := IdentitySecurityMutationTicket{
		TicketID: "ticket", AccountID: "account", Operation: "password_enroll",
		ExpiresAt: time.Now().Add(time.Minute),
	}
	body := `{"mutation_ticket_id":"ticket","step_up_receipt_id":"step","idempotency_key":"idem-key"}`
	for name, testCase := range map[string]struct {
		err  error
		code int
		body string
	}{
		"unavailable": {err: ErrIdentitySecurityUnavailable, code: http.StatusServiceUnavailable, body: "identity_security_unavailable"},
		"rejected":    {err: ErrIdentitySecurityRejected, code: http.StatusForbidden, body: "identity_security_mutation_rejected"},
	} {
		t.Run(name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, "/v1/accounts/account/password/enroll", strings.NewReader(body))
			req.Header.Set("Idempotency-Key", "idem-key")
			res := httptest.NewRecorder()
			identitySecurityTestHandler("account", identitySecurityTestResolver{ticket: ticket}, &identitySecurityTestStore{err: testCase.err}).ServeHTTP(res, req)
			if res.Code != testCase.code || !strings.Contains(res.Body.String(), testCase.body) {
				t.Fatalf("unexpected safe error response: %d %s", res.Code, res.Body.String())
			}
		})
	}

	res := httptest.NewRecorder()
	identitySecurityTestHandler("account", nil, &identitySecurityTestStore{err: errors.New("database detail")}).ServeHTTP(
		res, httptest.NewRequest(http.MethodGet, "/v1/accounts/account/security", nil),
	)
	if res.Code != http.StatusServiceUnavailable || strings.Contains(res.Body.String(), "database detail") {
		t.Fatalf("unsafe posture error response: %d %s", res.Code, res.Body.String())
	}
}

func TestIdentitySecurityHTTPMutationFailsClosedWithoutTrustedTicketResolver(t *testing.T) {
	store := &identitySecurityTestStore{}
	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/accounts/account/password/enroll",
		strings.NewReader(`{"mutation_ticket_id":"ticket","step_up_receipt_id":"step","idempotency_key":"idem-key"}`),
	)
	req.Header.Set("Idempotency-Key", "idem-key")
	res := httptest.NewRecorder()
	identitySecurityTestHandler("account", nil, store).ServeHTTP(res, req)
	if res.Code != http.StatusServiceUnavailable ||
		!strings.Contains(res.Body.String(), "identity_security_unavailable") {
		t.Fatalf("mutation did not fail closed without trusted resolver: %d %s", res.Code, res.Body.String())
	}
	if store.mutation.Operation != "" {
		t.Fatalf("mutation reached PostgreSQL boundary without trusted resolver: %#v", store.mutation)
	}
}

func TestIdentitySecurityHTTPPostureIsSecretSafe(t *testing.T) {
	res := httptest.NewRecorder()
	identitySecurityTestHandler("account", nil, &identitySecurityTestStore{}).ServeHTTP(res, httptest.NewRequest(http.MethodGet, "/v1/accounts/account/security", nil))
	if res.Code != http.StatusOK || !strings.Contains(res.Body.String(), `"password_status":"absent"`) || strings.Contains(res.Body.String(), "secret") {
		t.Fatalf("unsafe posture: %d %s", res.Code, res.Body.String())
	}
}

func identitySecurityServiceHTTPTestHandler(
	t *testing.T,
	processor *identitySecurityServiceTestProcessor,
	store *identitySecurityServiceTestStore,
) http.Handler {
	t.Helper()
	service := newIdentitySecurityServiceTestSubject(
		t,
		processor,
		&identitySecurityServiceTestIssuer{},
		store,
		time.Date(2026, 7, 24, 8, 0, 0, 0, time.UTC),
	)
	session := identitySecurityServiceTestSession()
	return NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		IdentitySessions:        identityHTTPTestSessionResolver{session: session},
		IdentitySecurityService: service,
	})
}

func identitySecurityServiceHTTPRequest(
	method string,
	path string,
	body string,
) *http.Request {
	request := httptest.NewRequest(
		method,
		"https://api.example.test"+path,
		strings.NewReader(body),
	)
	request.Header.Set("Origin", "https://api.example.test")
	request.Header.Set("Sec-Fetch-Site", "same-origin")
	request.Header.Set("Idempotency-Key", "password-change-1")
	return request
}

func TestIdentitySecurityServiceHTTPPasswordBeginReturnsNoStoreSafeProjection(t *testing.T) {
	processor := &identitySecurityServiceTestProcessor{
		processResult: identitySecurityServiceTestProcessResult(),
		handoffs:      map[string]IdentitySecuritySecretHandoff{},
	}
	store := &identitySecurityServiceTestStore{
		result: IdentitySecurityHTTPMutationResultDTO{
			PasswordStatus:           "set",
			SecurityVersion:          2,
			SessionsRevoked:          1,
			ReauthenticationRequired: true,
		},
	}
	handler := identitySecurityServiceHTTPTestHandler(t, processor, store)
	request := identitySecurityServiceHTTPRequest(
		http.MethodPost,
		"/v1/accounts/"+identitySecurityServiceTestAccountID+
			"/password/change/begin",
		`{"idempotency_key":"password-change-1","password":"TwelveChars1!"}`,
	)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK ||
		!strings.Contains(response.Body.String(), `"password_status":"set"`) ||
		!strings.Contains(response.Body.String(), `"two_factor_optional":true`) ||
		!strings.Contains(response.Body.String(), `"two_factor_recommended":true`) {
		t.Fatalf("password begin failed: %d %s", response.Code, response.Body.String())
	}
	if response.Header().Get("Cache-Control") != "no-store" ||
		response.Header().Get("Pragma") != "no-cache" ||
		response.Header().Get("X-Content-Type-Options") != "nosniff" {
		t.Fatalf("security response lost no-store headers: %#v", response.Header())
	}
	for _, forbidden := range []string{
		"secret_ref", "secret_digest", "ticket_id", "receipt",
		processor.processResult.SecretRef,
		processor.processResult.SecretDigest,
	} {
		if strings.Contains(response.Body.String(), forbidden) {
			t.Fatalf("security response exposed %q: %s", forbidden, response.Body.String())
		}
	}
	if len(processor.processCalls) != 1 ||
		processor.processCalls[0].AccountID != identitySecurityServiceTestAccountID ||
		processor.processCalls[0].Operation != "password_change" {
		t.Fatalf("HTTP boundary lost canonical binding: %#v", processor.processCalls)
	}
}

func TestIdentitySecurityServiceHTTPMFAUsesExplicitChallengeID(t *testing.T) {
	processResult := identitySecurityServiceTestProcessResult()
	processResult.ConfirmationChallengeID = "isc_" + strings.Repeat("B", 24)
	processResult.HandoffID = "ish_" + strings.Repeat("C", 24)
	processor := &identitySecurityServiceTestProcessor{
		processResult: processResult,
		confirmResult: IdentitySecuritySecretConfirmResult{
			RecoveryBatchDigest: strings.Repeat("b", 64),
			RecoveryCodeCount:   6,
			KeyVersion:          "key-v1",
			HandoffID:           "ish_" + strings.Repeat("E", 24),
			CleanupToken:        "isx_" + strings.Repeat("F", 24),
		},
		handoffs: map[string]IdentitySecuritySecretHandoff{
			"mfa_enroll": {
				ProvisioningURI: "otpauth://totp/ReleaseFoundry:test?secret=ABCDEF234567",
			},
			"mfa_confirm": {
				RecoveryCodes: []string{
					"A1BC-DEFG", "B2CD-EFGH", "C3DE-FGHJ",
					"D4EF-GHJK", "E5FG-HJKL", "F6GH-JKLM",
				},
			},
		},
	}
	store := &identitySecurityServiceTestStore{
		result: IdentitySecurityHTTPMutationResultDTO{
			TwoFactorStatus:      "pending",
			ConfirmationRequired: true,
		},
	}
	handler := identitySecurityServiceHTTPTestHandler(t, processor, store)
	beginRequest := identitySecurityServiceHTTPRequest(
		http.MethodPost,
		"/v1/accounts/"+identitySecurityServiceTestAccountID+
			"/two-factor/enroll/begin",
		`{"idempotency_key":"mfa-enroll-1"}`,
	)
	beginRequest.Header.Set("Idempotency-Key", "mfa-enroll-1")
	beginResponse := httptest.NewRecorder()
	handler.ServeHTTP(beginResponse, beginRequest)
	if beginResponse.Code != http.StatusOK ||
		!strings.Contains(
			beginResponse.Body.String(),
			`"confirmation_challenge_id":"`+
				processResult.ConfirmationChallengeID+`"`,
		) ||
		!strings.Contains(beginResponse.Body.String(), `"provisioning_uri":"otpauth://`) {
		t.Fatalf("MFA begin lost explicit challenge handoff: %d %s", beginResponse.Code, beginResponse.Body.String())
	}

	store.result = IdentitySecurityHTTPMutationResultDTO{
		TwoFactorStatus:          "enabled",
		RecoveryCodesRemaining:   6,
		ReauthenticationRequired: true,
	}
	confirmRequest := identitySecurityServiceHTTPRequest(
		http.MethodPost,
		"/v1/accounts/"+identitySecurityServiceTestAccountID+
			"/two-factor/enroll/confirm",
		`{"idempotency_key":"mfa-confirm-1","challenge_id":"`+
			processResult.ConfirmationChallengeID+`","code":"123456"}`,
	)
	confirmRequest.Header.Set("Idempotency-Key", "mfa-confirm-1")
	confirmResponse := httptest.NewRecorder()
	handler.ServeHTTP(confirmResponse, confirmRequest)
	if confirmResponse.Code != http.StatusOK ||
		!strings.Contains(confirmResponse.Body.String(), `"two_factor_status":"enabled"`) ||
		!strings.Contains(confirmResponse.Body.String(), `"recovery_codes":[`) {
		t.Fatalf("MFA confirm failed: %d %s", confirmResponse.Code, confirmResponse.Body.String())
	}
	if len(processor.confirmCalls) != 1 ||
		processor.confirmCalls[0].ChallengeID != processResult.ConfirmationChallengeID {
		t.Fatalf("A3 challenge_id was not bound to confirm: %#v", processor.confirmCalls)
	}
}

func TestIdentitySecurityServiceHTTPRejectsCSRFInjectionAndContractConfusion(t *testing.T) {
	baseProcessor := func() *identitySecurityServiceTestProcessor {
		return &identitySecurityServiceTestProcessor{
			processResult: identitySecurityServiceTestProcessResult(),
			handoffs:      map[string]IdentitySecuritySecretHandoff{},
		}
	}
	for name, mutate := range map[string]func(*http.Request){
		"missing origin": func(request *http.Request) {
			request.Header.Del("Origin")
		},
		"cross origin": func(request *http.Request) {
			request.Header.Set("Origin", "https://attacker.example.test")
		},
		"cross site": func(request *http.Request) {
			request.Header.Set("Sec-Fetch-Site", "cross-site")
		},
		"idempotency mismatch": func(request *http.Request) {
			request.Header.Set("Idempotency-Key", "different-key")
		},
	} {
		t.Run(name, func(t *testing.T) {
			processor := baseProcessor()
			handler := identitySecurityServiceHTTPTestHandler(
				t,
				processor,
				&identitySecurityServiceTestStore{
					result: IdentitySecurityHTTPMutationResultDTO{
						PasswordStatus:           "set",
						ReauthenticationRequired: true,
					},
				},
			)
			request := identitySecurityServiceHTTPRequest(
				http.MethodPost,
				"/v1/accounts/"+identitySecurityServiceTestAccountID+
					"/password/change/begin",
				`{"idempotency_key":"password-change-1","password":"TwelveChars1!"}`,
			)
			mutate(request)
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != http.StatusForbidden &&
				response.Code != http.StatusBadRequest {
				t.Fatalf("unsafe request was not rejected: %d %s", response.Code, response.Body.String())
			}
			if len(processor.processCalls) != 0 {
				t.Fatalf("unsafe request reached processor: %#v", processor.processCalls)
			}
		})
	}

	for _, field := range []string{
		"account_id", "actor_id", "session_id", "secret_ref",
		"secret_digest", "mutation_ticket_id", "step_up_receipt_id",
	} {
		t.Run("body "+field, func(t *testing.T) {
			processor := baseProcessor()
			handler := identitySecurityServiceHTTPTestHandler(
				t,
				processor,
				&identitySecurityServiceTestStore{},
			)
			body := `{"idempotency_key":"password-change-1","password":"TwelveChars1!","` +
				field + `":"injected"}`
			request := identitySecurityServiceHTTPRequest(
				http.MethodPost,
				"/v1/accounts/"+identitySecurityServiceTestAccountID+
					"/password/change/begin",
				body,
			)
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != http.StatusBadRequest ||
				!strings.Contains(
					response.Body.String(),
					"invalid_identity_security_request",
				) {
				t.Fatalf("injected %s was not rejected: %d %s", field, response.Code, response.Body.String())
			}
			if len(processor.processCalls) != 0 {
				t.Fatalf("injected body reached processor: %#v", processor.processCalls)
			}
		})
	}
}

func TestIdentitySecurityServiceHTTPPreservesOpaqueLegacyMutationBoundary(t *testing.T) {
	processor := &identitySecurityServiceTestProcessor{
		processResult: identitySecurityServiceTestProcessResult(),
		handoffs:      map[string]IdentitySecuritySecretHandoff{},
	}
	store := &identitySecurityServiceTestStore{}
	service := newIdentitySecurityServiceTestSubject(
		t,
		processor,
		&identitySecurityServiceTestIssuer{},
		store,
		time.Date(2026, 7, 24, 8, 0, 0, 0, time.UTC),
	)
	handler := NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		IdentitySessions: identityHTTPTestSessionResolver{
			session: identitySecurityServiceTestSession(),
		},
		IdentitySecurityService: service,
		IdentitySecurityTickets: identitySecurityTestResolver{},
		IdentitySecurity:        store,
	})
	request := identitySecurityServiceHTTPRequest(
		http.MethodPost,
		"/v1/accounts/"+identitySecurityServiceTestAccountID+
			"/password/change",
		`{"idempotency_key":"password-change-1","password":"TwelveChars1!"}`,
	)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest ||
		!strings.Contains(response.Body.String(), "secret_input_rejected") {
		t.Fatalf("legacy opaque endpoint accepted raw secret: %d %s", response.Code, response.Body.String())
	}
	if len(processor.processCalls) != 0 || len(store.mutations) != 0 {
		t.Fatalf("legacy rejection reached trusted dependencies")
	}
}
