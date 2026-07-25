package ashrclone

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/lib/pq"
)

func TestPostgresTenancyStoreQueryUsesOnlyScopedEntrypoint(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	store, err := newPostgresTenancyStore(
		db,
		5*time.Second,
		4*time.Second,
		2*time.Second,
	)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 7, 25, 1, 2, 3, 0, time.UTC)
	payload := `{
	  "schema_version":"ashr.clone.tenancy.v1",
	  "items":[{
	    "schema_version":"ashr.clone.tenancy.v1",
	    "organization_id":"` + tenancyTestOrganizationID + `",
	    "project_id":"` + tenancyTestProjectID + `",
	    "slug":"core-api",
	    "display_name":"Core API",
	    "status":"active",
	    "created_at":"` + now.Format(time.RFC3339) + `",
	    "updated_at":"` + now.Format(time.RFC3339) + `",
	    "archived_at":null
	  }],
	  "count":1
	}`
	mock.ExpectBegin()
	mock.ExpectExec("SELECT set_config").
		WithArgs("4000ms", "2000ms").
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery("SELECT a1_tenancy_query").
		WithArgs(
			tenancyTestAccountID,
			TenancyOperationProjectList,
			tenancyTestOrganizationID,
			nil,
		).
		WillReturnRows(sqlmock.NewRows([]string{"a1_tenancy_query"}).AddRow([]byte(payload)))
	mock.ExpectCommit()

	result, err := store.QueryTenancy(context.Background(), TenancyQuery{
		ActorPrincipalID: tenancyTestAccountID,
		Operation:        TenancyOperationProjectList,
		OrganizationID:   tenancyTestOrganizationID,
	})
	if err != nil {
		t.Fatal(err)
	}
	projects, ok := result.Items.([]TenancyProject)
	if !ok || len(projects) != 1 ||
		projects[0].ProjectID != tenancyTestProjectID ||
		result.SchemaVersion != TenancySchemaVersion || result.Count != 1 {
		t.Fatalf("unexpected parsed result: %#v", result)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresTenancyStoreMutationNormalizesAndHashesWithoutReturningDigests(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	store, err := newPostgresTenancyStore(
		db,
		5*time.Second,
		4*time.Second,
		2*time.Second,
	)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 7, 25, 1, 2, 3, 0, time.UTC)
	payload := `{
	  "schema_version":"ashr.clone.tenancy.v1",
	  "organization_id":"` + tenancyTestOrganizationID + `",
	  "project_id":"` + tenancyTestProjectID + `",
	  "environment_id":"` + tenancyTestEnvironmentID + `",
	  "name":"prod-cn",
	  "kind":"production",
	  "status":"active",
	  "created_at":"` + now.Format(time.RFC3339) + `",
	  "updated_at":"` + now.Format(time.RFC3339) + `",
	  "disabled_at":null
	}`
	mock.ExpectBegin()
	mock.ExpectExec("SELECT set_config").
		WithArgs("4000ms", "2000ms").
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery("FROM a1_tenancy_mutate").
		WithArgs(
			tenancyTestAccountID,
			TenancyOperationEnvironmentCreate,
			tenancyTestOrganizationID,
			tenancyTestProjectID,
			nil,
			nil,
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			"request_test_001",
			"trace/test:001",
			`{"kind":"production","name":"prod-cn"}`,
		).
		WillReturnRows(sqlmock.NewRows(
			[]string{"result_payload", "idempotent_replay", "completed_at"},
		).AddRow([]byte(payload), false, now))
	mock.ExpectCommit()

	result, err := store.MutateTenancy(context.Background(), TenancyMutation{
		ActorPrincipalID: tenancyTestAccountID,
		Operation:        TenancyOperationEnvironmentCreate,
		OrganizationID:   tenancyTestOrganizationID,
		ProjectID:        tenancyTestProjectID,
		IdempotencyKey:   "idem-test-001",
		RequestID:        "request_test_001",
		TraceID:          "trace/test:001",
		Payload: map[string]any{
			"name": " PROD-CN ",
			"kind": " Production ",
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	environment, ok := result.Result.(TenancyEnvironment)
	if !ok || environment.EnvironmentID != tenancyTestEnvironmentID ||
		result.IdempotentReplay || !result.CompletedAt.Equal(now) {
		t.Fatalf("unexpected mutation result: %#v", result)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestTenancyPostgresParsersRejectPrivateOrCrossScopePayloads(t *testing.T) {
	now := time.Date(2026, 7, 25, 1, 2, 3, 0, time.UTC).Format(time.RFC3339)
	tests := []string{
		`{"schema_version":"ashr.clone.tenancy.v1","items":[],"count":0,"request_digest":"hidden"}`,
		`{"schema_version":"ashr.clone.tenancy.v1","items":[{"schema_version":"ashr.clone.tenancy.v1","organization_id":"` + tenancyTestOrganizationID + `","project_id":"` + tenancyTestProjectID + `","slug":"core-api","display_name":"Core","status":"active","created_at":"` + now + `","updated_at":"` + now + `","archived_at":null,"secret_ref":"vault://hidden"}],"count":1}`,
		`{"schema_version":"ashr.clone.tenancy.v1","items":[{"schema_version":"ashr.clone.tenancy.v1","organization_id":"` + tenancyTestTargetID + `","project_id":"` + tenancyTestProjectID + `","slug":"core-api","display_name":"Core","status":"active","created_at":"` + now + `","updated_at":"` + now + `","archived_at":null}],"count":1}`,
	}
	for index, payload := range tests {
		_, err := parseTenancyListResult(TenancyQuery{
			ActorPrincipalID: tenancyTestAccountID,
			Operation:        TenancyOperationProjectList,
			OrganizationID:   tenancyTestOrganizationID,
		}, []byte(payload))
		if !errors.Is(err, ErrTenancyUnavailable) {
			t.Fatalf("case %d error = %v, want unavailable", index, err)
		}
	}
}

func TestTenancyDigestAndInputValidationAreStable(t *testing.T) {
	first := tenancySHA256("domain", "a", "bc")
	second := tenancySHA256("domain", "ab", "c")
	if first == second || len(first) != 64 || len(second) != 64 {
		t.Fatalf("domain-separated digest framing failed: %q %q", first, second)
	}
	mutation, payload, err := normalizeTenancyMutation(TenancyMutation{
		ActorPrincipalID: tenancyTestAccountID,
		Operation:        TenancyOperationProjectUpdate,
		OrganizationID:   tenancyTestOrganizationID,
		ProjectID:        tenancyTestProjectID,
		IdempotencyKey:   "idem-test-001",
		RequestID:        "request_test_001",
		Payload: map[string]any{
			"slug":         " CORE-API ",
			"display_name": " Core API ",
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if mutation.Payload["slug"] != "core-api" ||
		mutation.Payload["display_name"] != "Core API" ||
		string(payload) != `{"display_name":"Core API","slug":"core-api"}` {
		t.Fatalf("payload was not canonical: %#v %s", mutation.Payload, payload)
	}
	for _, invalid := range []string{
		"short",
		" leading-space",
		"contains whitespace",
		strings.Repeat("a", 129),
	} {
		if validTenancyIdempotencyKey(invalid) {
			t.Fatalf("invalid idempotency key accepted: %q", invalid)
		}
	}
}

func TestMapPostgresTenancyErrorReturnsOnlyStableDomains(t *testing.T) {
	tests := []struct {
		err  error
		want error
	}{
		{&pq.Error{Code: "42501", Message: "tenancy_authentication_required"}, ErrTenancyAuthenticationRequired},
		{&pq.Error{Code: "23505", Message: "tenancy_idempotency_conflict"}, ErrTenancyIdempotencyConflict},
		{&pq.Error{Code: "P0002", Message: "tenancy_not_found"}, ErrTenancyNotFound},
		{&pq.Error{Code: "P0003", Message: "tenancy_last_owner"}, ErrTenancyLastOwner},
		{&pq.Error{Code: "55000", Message: "tenancy_state_conflict"}, ErrTenancyStateConflict},
		{&pq.Error{Code: "23505", Message: "duplicate key secret constraint"}, ErrTenancyStateConflict},
		{&pq.Error{Code: "40P01", Message: "deadlock on private table"}, ErrTenancyUnavailable},
		{errors.New("driver leaked raw SQL"), ErrTenancyUnavailable},
	}
	for _, test := range tests {
		mapped := mapPostgresTenancyError(test.err)
		if !errors.Is(mapped, test.want) || mapped.Error() != test.want.Error() {
			t.Fatalf("map(%T %v) = %v, want %v", test.err, test.err, mapped, test.want)
		}
	}
}
