package ashrclone

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"testing"
	"time"
)

const tenancyPostgresIntegrationFlag = "ASHR_RUN_TENANCY_POSTGRES_INTEGRATION"

func tenancyLiveIdempotencyKey(scope string) string {
	return strings.Join([]string{"tenancy", "live", scope, "001"}, "-")
}

type tenancyPostgresLiveSessionResolver struct {
	session IdentityHTTPSession
}

func (resolver tenancyPostgresLiveSessionResolver) ResolveIdentityHTTPSession(
	context.Context,
	*http.Request,
) (IdentityHTTPSession, error) {
	return resolver.session, nil
}

func TestTenancyPostgresIntegration(t *testing.T) {
	if os.Getenv(tenancyPostgresIntegrationFlag) != "1" {
		t.Skip("set " + tenancyPostgresIntegrationFlag +
			"=1 to run PostgreSQL tenancy integration tests")
	}
	adminDSN := strings.TrimSpace(os.Getenv("ASHR_TENANCY_TEST_DSN"))
	if adminDSN == "" {
		adminDSN = strings.TrimSpace(
			os.Getenv("ASHR_IDENTITY_LIFECYCLE_TEST_DSN"),
		)
	}
	if adminDSN == "" {
		t.Skip("ASHR_TENANCY_TEST_DSN or " +
			"ASHR_IDENTITY_LIFECYCLE_TEST_DSN is not configured")
	}

	harness := newPostgresLifecycleHarness(t, adminDSN)
	sessionKey := make([]byte, 32)
	if _, err := rand.Read(sessionKey); err != nil {
		t.Fatalf("generate ephemeral tenancy integration session key: %v", err)
	}
	instance := harness.newInstance(
		t,
		sessionKey,
		"tenancy-live",
		nil,
	)
	store, err := instance.store.NewPostgresTenancyStore()
	if err != nil {
		t.Fatalf("construct PostgreSQL tenancy store: %v", err)
	}

	const (
		actorID      = "71000000-0000-4000-8000-000000000001"
		otherActorID = "71000000-0000-4000-8000-000000000002"
	)
	mustExecArgs(t, harness.adminDB, `
INSERT INTO identity_principals(id,status,metadata)
VALUES
  ($1::uuid,'active','{"source":"tenancy-live"}'::jsonb),
  ($2::uuid,'active','{"source":"tenancy-live"}'::jsonb)
`, actorID, otherActorID)

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	organizationMutation := TenancyMutation{
		ActorPrincipalID: actorID,
		Operation:        TenancyOperationOrganizationCreate,
		IdempotencyKey:   tenancyLiveIdempotencyKey("organization"),
		RequestID:        "request_tenancy_live_organization_001",
		TraceID:          "trace/tenancy/live:organization:001",
		Payload: map[string]any{
			"slug":         "tenancy-live-org",
			"display_name": "Tenancy Live Organization",
		},
	}
	firstOrganization, err := store.MutateTenancy(ctx, organizationMutation)
	if err != nil {
		t.Fatalf("create organization through Go store: %v", err)
	}
	if firstOrganization.IdempotentReplay {
		t.Fatal("first organization mutation was marked as replay")
	}
	organization, ok := firstOrganization.Result.(TenancyOrganization)
	if !ok || organization.OrganizationID == "" ||
		organization.Slug != "tenancy-live-org" {
		t.Fatalf("unexpected organization DTO: %#v", firstOrganization.Result)
	}

	replayedOrganization, err := store.MutateTenancy(ctx, organizationMutation)
	if err != nil {
		t.Fatalf("replay organization through Go store: %v", err)
	}
	replayedDTO, ok := replayedOrganization.Result.(TenancyOrganization)
	if !ok || !replayedOrganization.IdempotentReplay ||
		replayedDTO.OrganizationID != organization.OrganizationID ||
		!replayedOrganization.CompletedAt.Equal(firstOrganization.CompletedAt) {
		t.Fatalf("organization replay was not exact: %#v", replayedOrganization)
	}

	conflictingOrganization := organizationMutation
	conflictingOrganization.Payload = map[string]any{
		"slug":         "tenancy-live-org",
		"display_name": "Conflicting Organization",
	}
	if _, err := store.MutateTenancy(
		ctx,
		conflictingOrganization,
	); !errors.Is(err, ErrTenancyIdempotencyConflict) {
		t.Fatalf("organization payload conflict returned %v", err)
	}

	projectMutation := TenancyMutation{
		ActorPrincipalID: actorID,
		Operation:        TenancyOperationProjectCreate,
		OrganizationID:   organization.OrganizationID,
		IdempotencyKey:   tenancyLiveIdempotencyKey("project"),
		RequestID:        "request_tenancy_live_project_001",
		TraceID:          "trace/tenancy/live:project:001",
		Payload: map[string]any{
			"slug":         "tenancy-live-project",
			"display_name": "Tenancy Live Project",
		},
	}
	projectResult, err := store.MutateTenancy(ctx, projectMutation)
	if err != nil {
		t.Fatalf("create project through Go store: %v", err)
	}
	project, ok := projectResult.Result.(TenancyProject)
	if !ok || project.OrganizationID != organization.OrganizationID ||
		project.ProjectID == "" {
		t.Fatalf("unexpected project DTO: %#v", projectResult.Result)
	}

	organizations, err := store.QueryTenancy(ctx, TenancyQuery{
		ActorPrincipalID: actorID,
		Operation:        TenancyOperationOrganizationList,
	})
	if err != nil {
		t.Fatalf("list organizations through Go store: %v", err)
	}
	organizationItems, ok := organizations.Items.([]TenancyOrganization)
	if !ok || organizations.Count != 1 || len(organizationItems) != 1 ||
		organizationItems[0].OrganizationID != organization.OrganizationID {
		t.Fatalf("unexpected organization list: %#v", organizations)
	}

	otherOrganizationResult, err := store.MutateTenancy(ctx, TenancyMutation{
		ActorPrincipalID: otherActorID,
		Operation:        TenancyOperationOrganizationCreate,
		IdempotencyKey:   tenancyLiveIdempotencyKey("other-org"),
		RequestID:        "request_tenancy_live_other_org_001",
		Payload: map[string]any{
			"slug":         "tenancy-live-other",
			"display_name": "Tenancy Live Other",
		},
	})
	if err != nil {
		t.Fatalf("create cross-tenant organization: %v", err)
	}
	otherOrganization := otherOrganizationResult.Result.(TenancyOrganization)
	if _, err := store.QueryTenancy(ctx, TenancyQuery{
		ActorPrincipalID: actorID,
		Operation:        TenancyOperationProjectList,
		OrganizationID:   otherOrganization.OrganizationID,
	}); !errors.Is(err, ErrTenancyNotFound) {
		t.Fatalf("cross-tenant query returned %v", err)
	}

	if _, err := store.MutateTenancy(ctx, TenancyMutation{
		ActorPrincipalID: actorID,
		Operation:        TenancyOperationProjectMembershipRevoke,
		OrganizationID:   organization.OrganizationID,
		ProjectID:        project.ProjectID,
		TargetAccountID:  actorID,
		IdempotencyKey:   tenancyLiveIdempotencyKey("last-owner"),
		RequestID:        "request_tenancy_live_last_owner_001",
		Payload:          map[string]any{},
	}); !errors.Is(err, ErrTenancyLastOwner) {
		t.Fatalf("last-owner revoke returned %v", err)
	}

	concurrentMutation := TenancyMutation{
		ActorPrincipalID: actorID,
		Operation:        TenancyOperationEnvironmentCreate,
		OrganizationID:   organization.OrganizationID,
		ProjectID:        project.ProjectID,
		IdempotencyKey: tenancyLiveIdempotencyKey(
			"concurrent-environment",
		),
		RequestID: "request_tenancy_live_concurrent_environment_001",
		TraceID:   "trace/tenancy/live:environment:001",
		Payload: map[string]any{
			"name": "live-concurrent",
			"kind": "sandbox",
		},
	}
	const concurrentCalls = 12
	results := make(chan TenancyMutationResult, concurrentCalls)
	failures := make(chan error, concurrentCalls)
	var wait sync.WaitGroup
	for index := 0; index < concurrentCalls; index++ {
		wait.Add(1)
		go func() {
			defer wait.Done()
			result, mutationErr := store.MutateTenancy(ctx, concurrentMutation)
			if mutationErr != nil {
				failures <- mutationErr
				return
			}
			results <- result
		}()
	}
	wait.Wait()
	close(results)
	close(failures)
	for mutationErr := range failures {
		t.Fatalf("concurrent Go tenancy mutation: %v", mutationErr)
	}
	firstEffects := 0
	environmentID := ""
	for result := range results {
		if !result.IdempotentReplay {
			firstEffects++
		}
		environment, ok := result.Result.(TenancyEnvironment)
		if !ok {
			t.Fatalf("unexpected concurrent environment DTO: %#v", result.Result)
		}
		if environmentID == "" {
			environmentID = environment.EnvironmentID
		} else if environment.EnvironmentID != environmentID {
			t.Fatalf(
				"concurrent replay created multiple environments: %s != %s",
				environment.EnvironmentID,
				environmentID,
			)
		}
	}
	if firstEffects != 1 || environmentID == "" {
		t.Fatalf(
			"concurrent replay effects=%d environment_id=%q",
			firstEffects,
			environmentID,
		)
	}

	handler := NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		BackendName: "postgres_tenancy_live",
		Tenancy:     store,
		IdentitySessions: tenancyPostgresLiveSessionResolver{
			session: IdentityHTTPSession{
				AccountID: actorID,
				ActorID:   otherActorID,
				SessionID: "tenancy-live-session",
			},
		},
	})
	httpRequest := httptest.NewRequest(
		http.MethodPost,
		fmt.Sprintf(
			"/v1/organizations/%s/projects/%s/environments",
			organization.OrganizationID,
			project.ProjectID,
		),
		strings.NewReader(
			`{"name":"live-http","kind":"development"}`,
		),
	)
	httpRequest.Header.Set("Content-Type", "application/json")
	httpRequest.Header.Set("Idempotency-Key", "tenancy-live-http-environment-001")
	httpRequest.Header.Set("X-Request-ID", "request_tenancy_live_http_001")
	httpRecorder := httptest.NewRecorder()
	handler.ServeHTTP(httpRecorder, httpRequest)
	if httpRecorder.Code != http.StatusCreated {
		t.Fatalf(
			"live Go HTTP create status=%d body=%s",
			httpRecorder.Code,
			httpRecorder.Body.String(),
		)
	}
	if httpRecorder.Header().Get("Cache-Control") != "no-store" ||
		httpRecorder.Header().Get("X-Content-Type-Options") != "nosniff" {
		t.Fatalf("live Go HTTP security headers: %#v", httpRecorder.Header())
	}
	var envelope struct {
		SchemaVersion    string             `json:"schema_version"`
		Result           TenancyEnvironment `json:"result"`
		RequestID        string             `json:"request_id"`
		IdempotentReplay bool               `json:"idempotent_replay"`
	}
	decoder := json.NewDecoder(httpRecorder.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&envelope); err != nil {
		t.Fatalf("decode live Go HTTP response: %v", err)
	}
	if envelope.SchemaVersion != TenancySchemaVersion ||
		envelope.RequestID != "request_tenancy_live_http_001" ||
		envelope.IdempotentReplay ||
		envelope.Result.OrganizationID != organization.OrganizationID ||
		envelope.Result.ProjectID != project.ProjectID ||
		envelope.Result.Name != "live-http" {
		t.Fatalf("unexpected live Go HTTP envelope: %#v", envelope)
	}
}
