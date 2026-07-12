package ashrclone

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

func (r identitySecurityTestResolver) ResolveIdentitySecurityMutationTicket(context.Context, string, string, string) (IdentitySecurityMutationTicket, error) {
	return r.ticket, r.err
}

type identitySecurityTestStore struct {
	mutation IdentitySecurityMutation
	result   JSONMap
}

func (s *identitySecurityTestStore) GetIdentitySecurityPosture(context.Context, string) (JSONMap, error) {
	return JSONMap{"password_status": "absent", "two_factor_status": "disabled"}, nil
}

func (s *identitySecurityTestStore) MutateIdentitySecurity(_ context.Context, mutation IdentitySecurityMutation) (JSONMap, error) {
	s.mutation = mutation
	return s.result, nil
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
		body := `{"mutation_ticket_id":"ticket","step_up_receipt_id":"step","idempotency_key":"idem","` + field + `":"private"}`
		req := httptest.NewRequest(http.MethodPost, "/v1/accounts/account/password/enroll", strings.NewReader(body))
		req.Header.Set("Idempotency-Key", "idem")
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

func TestIdentitySecurityHTTPRequiresBoundTicketAndIdempotency(t *testing.T) {
	store := &identitySecurityTestStore{result: JSONMap{"password_status": "set", "sessions_revoked": 1}}
	ticket := IdentitySecurityMutationTicket{TicketID: "ticket", AccountID: "account", Operation: "password_enroll", ExpiresAt: time.Now().Add(time.Minute)}
	body := `{"mutation_ticket_id":"ticket","step_up_receipt_id":"step","idempotency_key":"idem"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/accounts/account/password/enroll", strings.NewReader(body))
	req.Header.Set("Idempotency-Key", "idem")
	res := httptest.NewRecorder()
	identitySecurityTestHandler("account", identitySecurityTestResolver{ticket: ticket}, store).ServeHTTP(res, req)
	if res.Code != http.StatusOK || !strings.Contains(res.Body.String(), IdentitySecurityHTTPSchemaVersion) {
		t.Fatalf("mutation failed: %d %s", res.Code, res.Body.String())
	}
	if store.mutation.AccountID != "account" || store.mutation.ActorID != "account" || store.mutation.Operation != "password_enroll" || store.mutation.IdempotencyKey != "idem" {
		t.Fatalf("trusted mutation lost binding: %#v", store.mutation)
	}

	for name, resolver := range map[string]IdentitySecurityTicketResolver{
		"wrong account":   identitySecurityTestResolver{ticket: IdentitySecurityMutationTicket{AccountID: "other", Operation: "password_enroll", ExpiresAt: time.Now().Add(time.Minute)}},
		"wrong operation": identitySecurityTestResolver{ticket: IdentitySecurityMutationTicket{AccountID: "account", Operation: "password_change", ExpiresAt: time.Now().Add(time.Minute)}},
		"expired":         identitySecurityTestResolver{ticket: IdentitySecurityMutationTicket{AccountID: "account", Operation: "password_enroll", ExpiresAt: time.Now().Add(-time.Minute)}},
		"resolver error":  identitySecurityTestResolver{err: errors.New("private lookup failure")},
	} {
		t.Run(name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, "/v1/accounts/account/password/enroll", strings.NewReader(body))
			req.Header.Set("Idempotency-Key", "idem")
			res := httptest.NewRecorder()
			identitySecurityTestHandler("account", resolver, &identitySecurityTestStore{}).ServeHTTP(res, req)
			if res.Code != http.StatusForbidden || strings.Contains(res.Body.String(), "private lookup") {
				t.Fatalf("unsafe rejection: %d %s", res.Code, res.Body.String())
			}
		})
	}
}

func TestIdentitySecurityHTTPPostureIsSecretSafe(t *testing.T) {
	res := httptest.NewRecorder()
	identitySecurityTestHandler("account", nil, &identitySecurityTestStore{}).ServeHTTP(res, httptest.NewRequest(http.MethodGet, "/v1/accounts/account/security", nil))
	if res.Code != http.StatusOK || !strings.Contains(res.Body.String(), `"password_status":"absent"`) || strings.Contains(res.Body.String(), "secret") {
		t.Fatalf("unsafe posture: %d %s", res.Code, res.Body.String())
	}
}
