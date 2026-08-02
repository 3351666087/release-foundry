package releasefoundry

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

const (
	tenancyTestAccountID      = "11111111-1111-4111-8111-111111111111"
	tenancyTestActorID        = "22222222-2222-4222-8222-222222222222"
	tenancyTestOrganizationID = "33333333-3333-4333-8333-333333333333"
	tenancyTestProjectID      = "44444444-4444-4444-8444-444444444444"
	tenancyTestEnvironmentID  = "55555555-5555-4555-8555-555555555555"
	tenancyTestTargetID       = "66666666-6666-4666-8666-666666666666"
)

type tenancyTestSessionResolver struct {
	session IdentityHTTPSession
	err     error
}

func (resolver tenancyTestSessionResolver) ResolveIdentityHTTPSession(
	context.Context,
	*http.Request,
) (IdentityHTTPSession, error) {
	return resolver.session, resolver.err
}

type tenancyTestStore struct {
	queryResult    TenancyListResult
	mutationResult TenancyMutationResult
	err            error
	queries        []TenancyQuery
	mutations      []TenancyMutation
}

func (store *tenancyTestStore) QueryTenancy(
	_ context.Context,
	query TenancyQuery,
) (TenancyListResult, error) {
	store.queries = append(store.queries, query)
	return store.queryResult, store.err
}

func (store *tenancyTestStore) MutateTenancy(
	_ context.Context,
	mutation TenancyMutation,
) (TenancyMutationResult, error) {
	store.mutations = append(store.mutations, mutation)
	return store.mutationResult, store.err
}

func newTenancyHTTPTestServer(store TenancyHTTPStore) http.Handler {
	return NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		BackendName: "postgres_test",
		Tenancy:     store,
		IdentitySessions: tenancyTestSessionResolver{
			session: IdentityHTTPSession{
				AccountID: tenancyTestAccountID,
				ActorID:   tenancyTestActorID,
				SessionID: "session-test",
			},
		},
	})
}

func TestTenancyHTTPRoutesUseCanonicalSessionAccount(t *testing.T) {
	now := time.Date(2026, 7, 25, 1, 2, 3, 0, time.UTC)
	tests := []struct {
		name      string
		method    string
		path      string
		body      string
		operation string
		mutation  bool
		status    int
	}{
		{"list organizations", http.MethodGet, "/v1/organizations", "", TenancyOperationOrganizationList, false, http.StatusOK},
		{"create organization", http.MethodPost, "/v1/organizations", `{"slug":"acme-org","display_name":"Acme"}`, TenancyOperationOrganizationCreate, true, http.StatusCreated},
		{"list projects", http.MethodGet, "/v1/organizations/" + tenancyTestOrganizationID + "/projects", "", TenancyOperationProjectList, false, http.StatusOK},
		{"create project", http.MethodPost, "/v1/organizations/" + tenancyTestOrganizationID + "/projects", `{"slug":"core-api","display_name":"Core API"}`, TenancyOperationProjectCreate, true, http.StatusCreated},
		{"update project", http.MethodPatch, "/v1/organizations/" + tenancyTestOrganizationID + "/projects/" + tenancyTestProjectID, `{"display_name":"Core API v2"}`, TenancyOperationProjectUpdate, true, http.StatusOK},
		{"archive project", http.MethodPost, "/v1/organizations/" + tenancyTestOrganizationID + "/projects/" + tenancyTestProjectID + "/archive", `{}`, TenancyOperationProjectArchive, true, http.StatusOK},
		{"restore project", http.MethodPost, "/v1/organizations/" + tenancyTestOrganizationID + "/projects/" + tenancyTestProjectID + "/restore", `{}`, TenancyOperationProjectRestore, true, http.StatusOK},
		{"list environments", http.MethodGet, "/v1/organizations/" + tenancyTestOrganizationID + "/projects/" + tenancyTestProjectID + "/environments", "", TenancyOperationEnvironmentList, false, http.StatusOK},
		{"create environment", http.MethodPost, "/v1/organizations/" + tenancyTestOrganizationID + "/projects/" + tenancyTestProjectID + "/environments", `{"name":"prod-cn","kind":"production"}`, TenancyOperationEnvironmentCreate, true, http.StatusCreated},
		{"disable environment", http.MethodPost, "/v1/organizations/" + tenancyTestOrganizationID + "/projects/" + tenancyTestProjectID + "/environments/" + tenancyTestEnvironmentID + "/disable", `{}`, TenancyOperationEnvironmentDisable, true, http.StatusOK},
		{"enable environment", http.MethodPost, "/v1/organizations/" + tenancyTestOrganizationID + "/projects/" + tenancyTestProjectID + "/environments/" + tenancyTestEnvironmentID + "/enable", `{}`, TenancyOperationEnvironmentEnable, true, http.StatusOK},
		{"list memberships", http.MethodGet, "/v1/organizations/" + tenancyTestOrganizationID + "/projects/" + tenancyTestProjectID + "/memberships", "", TenancyOperationProjectMembershipList, false, http.StatusOK},
		{"set membership", http.MethodPut, "/v1/organizations/" + tenancyTestOrganizationID + "/projects/" + tenancyTestProjectID + "/memberships/" + tenancyTestTargetID, `{"role":"developer"}`, TenancyOperationProjectMembershipSet, true, http.StatusOK},
		{"revoke membership", http.MethodDelete, "/v1/organizations/" + tenancyTestOrganizationID + "/projects/" + tenancyTestProjectID + "/memberships/" + tenancyTestTargetID, `{}`, TenancyOperationProjectMembershipRevoke, true, http.StatusOK},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			store := &tenancyTestStore{
				queryResult: TenancyListResult{
					SchemaVersion: TenancySchemaVersion,
					Items:         []TenancyOrganization{},
					Count:         0,
				},
				mutationResult: TenancyMutationResult{
					Result: TenancyOrganization{
						SchemaVersion:  TenancySchemaVersion,
						OrganizationID: tenancyTestOrganizationID,
						Slug:           "acme-org",
						DisplayName:    "Acme",
						Status:         "active",
						CreatedAt:      now,
						UpdatedAt:      now,
					},
					CompletedAt: now,
				},
			}
			request := httptest.NewRequest(test.method, test.path, strings.NewReader(test.body))
			request.Header.Set("X-Request-ID", "request_test_001")
			request.Header.Set("X-ReleaseFoundry-Trace-ID", "trace/test:001")
			if test.mutation {
				request.Header.Set("Content-Type", "application/json")
				request.Header.Set("Idempotency-Key", "idem-test-001")
			}
			recorder := httptest.NewRecorder()
			newTenancyHTTPTestServer(store).ServeHTTP(recorder, request)
			if recorder.Code != test.status {
				t.Fatalf("status = %d, want %d: %s", recorder.Code, test.status, recorder.Body.String())
			}
			if recorder.Header().Get("Cache-Control") != "no-store" ||
				recorder.Header().Get("X-Content-Type-Options") != "nosniff" {
				t.Fatalf("missing tenancy security headers: %#v", recorder.Header())
			}
			if test.mutation {
				if len(store.mutations) != 1 {
					t.Fatalf("mutations = %d, want 1", len(store.mutations))
				}
				mutation := store.mutations[0]
				if mutation.Operation != test.operation {
					t.Fatalf("operation = %q, want %q", mutation.Operation, test.operation)
				}
				if mutation.ActorPrincipalID != tenancyTestAccountID ||
					mutation.ActorPrincipalID == tenancyTestActorID {
					t.Fatalf("caller principal was not canonical Session account: %#v", mutation)
				}
				if mutation.RequestID != "request_test_001" ||
					mutation.TraceID != "trace/test:001" ||
					mutation.IdempotencyKey != "idem-test-001" {
					t.Fatalf("mutation correlation fields = %#v", mutation)
				}
			} else {
				if len(store.queries) != 1 {
					t.Fatalf("queries = %d, want 1", len(store.queries))
				}
				query := store.queries[0]
				if query.Operation != test.operation ||
					query.ActorPrincipalID != tenancyTestAccountID ||
					query.ActorPrincipalID == tenancyTestActorID {
					t.Fatalf("query trust boundary = %#v", query)
				}
			}
		})
	}
}

func TestTenancyHTTPRejectsOverridesUnknownFieldsAndInvalidIdempotency(t *testing.T) {
	tests := []struct {
		name       string
		configure  func(*http.Request)
		body       string
		wantCode   string
		wantStatus int
	}{
		{
			name: "header account override",
			configure: func(request *http.Request) {
				request.Header.Set("X-ReleaseFoundry-Account-ID", tenancyTestTargetID)
			},
			body:       `{"slug":"acme-org","display_name":"Acme"}`,
			wantCode:   "tenancy_invalid_request",
			wantStatus: http.StatusBadRequest,
		},
		{
			name: "query session override",
			configure: func(request *http.Request) {
				query := request.URL.Query()
				query.Set("session_id", "caller-controlled")
				request.URL.RawQuery = query.Encode()
			},
			body:       `{"slug":"acme-org","display_name":"Acme"}`,
			wantCode:   "tenancy_invalid_request",
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "unknown body field",
			body:       `{"slug":"acme-org","display_name":"Acme","actor_id":"` + tenancyTestTargetID + `"}`,
			wantCode:   "tenancy_invalid_request",
			wantStatus: http.StatusBadRequest,
		},
		{
			name: "missing idempotency key",
			configure: func(request *http.Request) {
				request.Header.Del("Idempotency-Key")
			},
			body:       `{"slug":"acme-org","display_name":"Acme"}`,
			wantCode:   "tenancy_invalid_idempotency_key",
			wantStatus: http.StatusBadRequest,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			store := &tenancyTestStore{}
			request := httptest.NewRequest(http.MethodPost, "/v1/organizations", strings.NewReader(test.body))
			request.Header.Set("Content-Type", "application/json")
			request.Header.Set("Idempotency-Key", "idem-test-001")
			if test.configure != nil {
				test.configure(request)
			}
			recorder := httptest.NewRecorder()
			newTenancyHTTPTestServer(store).ServeHTTP(recorder, request)
			if recorder.Code != test.wantStatus {
				t.Fatalf("status = %d, want %d: %s", recorder.Code, test.wantStatus, recorder.Body.String())
			}
			var body map[string]any
			if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
				t.Fatal(err)
			}
			if body["code"] != test.wantCode {
				t.Fatalf("code = %#v, want %q", body["code"], test.wantCode)
			}
			if len(body) != 4 || body["schema_version"] != TenancySchemaVersion ||
				body["request_id"] == "" {
				t.Fatalf("unsafe or incomplete tenancy error: %#v", body)
			}
			if len(store.queries) != 0 || len(store.mutations) != 0 {
				t.Fatalf("rejected request reached store")
			}
		})
	}
}

func TestTenancyHTTPAuthenticationAndDatabaseErrorsArePublicSafe(t *testing.T) {
	t.Run("missing session", func(t *testing.T) {
		server := NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
			Tenancy: &tenancyTestStore{},
		})
		request := httptest.NewRequest(http.MethodGet, "/v1/organizations", nil)
		recorder := httptest.NewRecorder()
		server.ServeHTTP(recorder, request)
		if recorder.Code != http.StatusUnauthorized ||
			!strings.Contains(recorder.Body.String(), "tenancy_authentication_required") {
			t.Fatalf("unexpected authentication response: %d %s", recorder.Code, recorder.Body.String())
		}
	})

	t.Run("database error", func(t *testing.T) {
		store := &tenancyTestStore{
			err: errors.New("pq: relation secret_table SQLSTATE 42P01"),
		}
		request := httptest.NewRequest(http.MethodGet, "/v1/organizations", nil)
		recorder := httptest.NewRecorder()
		newTenancyHTTPTestServer(store).ServeHTTP(recorder, request)
		if recorder.Code != http.StatusServiceUnavailable ||
			!strings.Contains(recorder.Body.String(), `"code":"tenancy_unavailable"`) {
			t.Fatalf("unexpected unavailable response: %d %s", recorder.Code, recorder.Body.String())
		}
		for _, forbidden := range []string{"secret_table", "SQLSTATE", "42P01", "relation"} {
			if strings.Contains(recorder.Body.String(), forbidden) {
				t.Fatalf("database detail leaked in %s", recorder.Body.String())
			}
		}
	})
}

func TestTenancyRouteAdvertisementRequiresInstalledAuthority(t *testing.T) {
	withoutTenancy := NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{})
	request := httptest.NewRequest(http.MethodGet, "/v1/openapi.json", nil)
	recorder := httptest.NewRecorder()
	withoutTenancy.ServeHTTP(recorder, request)
	if strings.Contains(recorder.Body.String(), "/v1/organizations") {
		t.Fatalf("memory runtime advertised authoritative tenancy routes")
	}

	withTenancy := newTenancyHTTPTestServer(&tenancyTestStore{})
	recorder = httptest.NewRecorder()
	withTenancy.ServeHTTP(recorder, request)
	for _, route := range []string{
		"/v1/organizations",
		"/v1/organizations/{organization_id}/projects",
		"/v1/organizations/{organization_id}/projects/{project_id}/environments",
		"/v1/organizations/{organization_id}/projects/{project_id}/memberships/{account_id}",
	} {
		if !strings.Contains(recorder.Body.String(), route) {
			t.Fatalf("installed tenancy authority did not advertise %s", route)
		}
	}
}
