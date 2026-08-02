package releasefoundry

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"regexp"
	"strings"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
)

func identitySecurityIssuerTestRequest(
	now time.Time,
) IdentitySecurityTicketIssueRequest {
	request := IdentitySecurityTicketIssueRequest{
		OrganizationID: identitySecurityServiceTestOrganizationID,
		ProjectID:      identitySecurityServiceTestProjectID,
		AccountID:      identitySecurityServiceTestAccountID,
		ActorID:        identitySecurityServiceTestAccountID,
		SessionID:      identitySecurityServiceTestSessionID,
		SessionDigest:  strings.Repeat("e", 64),
		Operation:      "password_change",
		IdempotencyKey: "password-change-1",
		SecretRef:      "isr_" + strings.Repeat("A", 24),
		SecretDigest:   strings.Repeat("a", 64),
		ExpiresAt:      now.Add(4 * time.Minute),
	}
	request.ContextDigest = identitySecurityTicketContextDigest(request)
	return request
}

func newIdentitySecurityIssuerTestSubject(
	t *testing.T,
	now time.Time,
) (*ProductionIdentitySecurityTicketIssuer, sqlmock.Sqlmock, *sql.DB) {
	t.Helper()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("open sqlmock: %v", err)
	}
	issuer, err := NewProductionIdentitySecurityTicketIssuer(
		ProductionIdentitySecurityTicketIssuerOptions{
			DB:               db,
			SQLTimeout:       5 * time.Second,
			StatementTimeout: 3 * time.Second,
			LockTimeout:      time.Second,
			Now:              func() time.Time { return now },
		},
	)
	if err != nil {
		_ = db.Close()
		t.Fatalf("construct issuer: %v", err)
	}
	return issuer, mock, db
}

func expectIdentitySecurityIssuerScope(
	mock sqlmock.Sqlmock,
	request IdentitySecurityTicketIssueRequest,
) {
	mock.ExpectExec("SELECT set_config").
		WithArgs(
			"3000ms",
			"1000ms",
			request.OrganizationID,
			request.ProjectID,
			request.AccountID,
		).
		WillReturnResult(sqlmock.NewResult(0, 1))
}

func TestProductionIdentitySecurityTicketIssuerRequiresIndependentSafePool(t *testing.T) {
	if _, err := NewProductionIdentitySecurityTicketIssuer(
		ProductionIdentitySecurityTicketIssuerOptions{},
	); err == nil {
		t.Fatal("issuer accepted a missing database")
	}
	db, _, err := sqlmock.New()
	if err != nil {
		t.Fatalf("open sqlmock: %v", err)
	}
	defer db.Close()
	for name, options := range map[string]ProductionIdentitySecurityTicketIssuerOptions{
		"SQL too large": {
			DB: db, SQLTimeout: 31 * time.Second,
		},
		"statement exceeds SQL": {
			DB: db, SQLTimeout: time.Second, StatementTimeout: 2 * time.Second,
		},
		"lock exceeds statement": {
			DB: db, SQLTimeout: 3 * time.Second,
			StatementTimeout: time.Second, LockTimeout: 2 * time.Second,
		},
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := NewProductionIdentitySecurityTicketIssuer(options); err == nil {
				t.Fatal("unsafe issuer timeout configuration was accepted")
			}
		})
	}
}

func TestProductionIdentitySecurityTicketIssuerReadinessChecksExactRoleAndACL(t *testing.T) {
	newCoreIssuer := "public.a1_issue_identity_security_mutation_ticket(" +
		"text,text,uuid,uuid,text,text,text,text,text,integer,text,integer," +
		"timestamp with time zone)"
	oldCoreIssuer := "public.a1_issue_identity_security_mutation_ticket(" +
		"text,text,uuid,uuid,text,text,text,text,text,integer," +
		"timestamp with time zone)"
	newScopedIssuer := "public.a1_issue_scoped_identity_security_mutation_ticket(" +
		"uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,text,integer," +
		"text,integer,timestamp with time zone)"
	oldScopedIssuer := "public.a1_issue_scoped_identity_security_mutation_ticket(" +
		"uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,text,integer," +
		"timestamp with time zone)"
	for _, required := range []string{
		"current_user = 'a1_security_ticket_issuer'",
		"NOT rolcanlogin",
		"pg_has_role(session_user, current_user, 'MEMBER')",
		"NOT rolbypassrls",
		"NOT has_schema_privilege(current_user, 'public', 'CREATE')",
		newScopedIssuer,
		newCoreIssuer,
		oldScopedIssuer + "'\n  ) IS NULL",
		oldCoreIssuer + "'\n  ) IS NULL",
		"a1_project_identity_security_processor_state",
		"a1_project_identity_security_mutation_replay",
		"a1_mutate_totp_recovery_lifecycle",
		"identity_account_security",
		"identity_security_receipts",
		"identity_security_mutation_tickets",
		"identity_security_mutation_idempotency",
		"identity_security_ticket_issuance",
		"SELECT count(*) = 5",
		"policy.roles = ARRAY['public'::name]",
		"has_any_column_privilege",
		"has_function_privilege('public', function_oid, 'EXECUTE')",
		"SELECT count(*) = 6",
		"function_row.prosecdef",
		"pg_get_userbyid(function_row.proowner) <> current_user",
		"NOT pg_catalog.pg_has_role(",
		"search_path=pg_catalog,public,pg_temp",
	} {
		if !strings.Contains(
			productionIdentitySecurityIssuerReadinessQuery,
			required,
		) {
			t.Fatalf("issuer readiness omitted %s", required)
		}
	}
	now := time.Date(2026, 7, 24, 8, 0, 0, 0, time.UTC)
	for name, ready := range map[string]bool{
		"ready": true, "unsafe ACL": false,
	} {
		t.Run(name, func(t *testing.T) {
			issuer, mock, db := newIdentitySecurityIssuerTestSubject(t, now)
			defer db.Close()
			mock.ExpectQuery(
				regexp.QuoteMeta(productionIdentitySecurityIssuerReadinessQuery),
			).WillReturnRows(sqlmock.NewRows([]string{"ready"}).AddRow(ready))
			err := issuer.Ready(context.Background())
			if ready && err != nil {
				t.Fatalf("safe issuer was not ready: %v", err)
			}
			if !ready && !errors.Is(err, ErrIdentitySecurityUnavailable) {
				t.Fatalf("unsafe issuer ACL was accepted: %v", err)
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatalf("issuer readiness expectations: %v", err)
			}
		})
	}
}

func TestProductionIdentitySecurityTicketIssuerIssuesScopedTicketAndAcceptsExactRetryExpiry(t *testing.T) {
	now := time.Date(2026, 7, 24, 8, 0, 0, 0, time.UTC)
	issuer, mock, db := newIdentitySecurityIssuerTestSubject(t, now)
	defer db.Close()
	request := identitySecurityIssuerTestRequest(now)
	request.ExpiresAt = request.ExpiresAt.Add(987 * time.Nanosecond)
	canonicalExpiresAt := request.ExpiresAt.UTC().Truncate(time.Microsecond)
	issuedProjection := IdentitySecurityIssuedTicket{
		TicketID:      strings.Repeat("c", 64),
		ReceiptID:     strings.Repeat("d", 64),
		ContextDigest: request.ContextDigest,
		// An exact retry must recover the first still-live ticket even when the
		// caller's newly computed expiry ceiling is later.
		ExpiresAt: now.Add(2 * time.Minute),
	}
	raw, err := json.Marshal(issuedProjection)
	if err != nil {
		t.Fatalf("marshal issuer projection: %v", err)
	}
	mock.ExpectBegin()
	expectIdentitySecurityIssuerScope(mock, request)
	mock.ExpectQuery("SELECT a1_issue_scoped_identity_security_mutation_ticket").
		WithArgs(
			request.OrganizationID,
			request.ProjectID,
			request.AccountID,
			request.ActorID,
			request.SessionID,
			request.SessionDigest,
			request.Operation,
			request.IdempotencyKey,
			request.ContextDigest,
			request.SecretRef,
			request.SecretDigest,
			request.ExpectedRecoveryBatchDigest,
			request.ExpectedRecoveryCodeCount,
			request.RecoveryBatchDigest,
			request.RecoveryCodeCount,
			canonicalExpiresAt,
		).
		WillReturnRows(sqlmock.NewRows([]string{"issued"}).AddRow(raw))
	mock.ExpectCommit()

	issued, err := issuer.IssueIdentitySecurityMutationTicket(
		context.Background(),
		request,
	)
	if err != nil {
		t.Fatalf("issue scoped ticket: %v", err)
	}
	if issued != issuedProjection {
		t.Fatalf("issuer projection changed: %#v", issued)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("issuer expectations: %v", err)
	}
}

func TestProductionIdentitySecurityTicketIssuerRejectsContextPayloadAndProjectionMismatch(t *testing.T) {
	now := time.Date(2026, 7, 24, 8, 0, 0, 0, time.UTC)
	for name, mutate := range map[string]func(*IdentitySecurityTicketIssueRequest){
		"context": func(request *IdentitySecurityTicketIssueRequest) {
			request.ContextDigest = strings.Repeat("f", 64)
		},
		"actor": func(request *IdentitySecurityTicketIssueRequest) {
			request.ActorID = identitySecurityServiceTestProjectID
			request.ContextDigest = identitySecurityTicketContextDigest(*request)
		},
		"secret ref": func(request *IdentitySecurityTicketIssueRequest) {
			request.SecretRef = "not-an-opaque-reference"
		},
		"expired": func(request *IdentitySecurityTicketIssueRequest) {
			request.ExpiresAt = now
		},
	} {
		t.Run(name, func(t *testing.T) {
			issuer, mock, db := newIdentitySecurityIssuerTestSubject(t, now)
			defer db.Close()
			request := identitySecurityIssuerTestRequest(now)
			mutate(&request)
			if _, err := issuer.IssueIdentitySecurityMutationTicket(
				context.Background(),
				request,
			); !errors.Is(err, ErrIdentitySecurityRejected) {
				t.Fatalf("unsafe issuer request was accepted: %v", err)
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatalf("invalid request reached database: %v", err)
			}
		})
	}

	issuer, mock, db := newIdentitySecurityIssuerTestSubject(t, now)
	defer db.Close()
	request := identitySecurityIssuerTestRequest(now)
	projection := IdentitySecurityIssuedTicket{
		TicketID:      strings.Repeat("c", 64),
		ReceiptID:     strings.Repeat("d", 64),
		ContextDigest: request.ContextDigest,
		ExpiresAt:     request.ExpiresAt.Add(time.Second),
	}
	raw, err := json.Marshal(projection)
	if err != nil {
		t.Fatalf("marshal invalid issuer projection: %v", err)
	}
	mock.ExpectBegin()
	expectIdentitySecurityIssuerScope(mock, request)
	mock.ExpectQuery("SELECT a1_issue_scoped_identity_security_mutation_ticket").
		WillReturnRows(sqlmock.NewRows([]string{"issued"}).AddRow(raw))
	mock.ExpectRollback()
	if _, err := issuer.IssueIdentitySecurityMutationTicket(
		context.Background(),
		request,
	); !errors.Is(err, ErrIdentitySecurityUnavailable) {
		t.Fatalf("invalid issuer projection was accepted: %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("invalid projection expectations: %v", err)
	}
}

func TestProductionIdentitySecurityTicketIssuerCancelIsScopedIdempotentAndSurvivesCallerCancellation(t *testing.T) {
	now := time.Date(2026, 7, 24, 8, 0, 0, 0, time.UTC)
	issuer, mock, db := newIdentitySecurityIssuerTestSubject(t, now)
	defer db.Close()
	request := identitySecurityIssuerTestRequest(now)
	issued := IdentitySecurityIssuedTicket{
		TicketID:      strings.Repeat("c", 64),
		ReceiptID:     strings.Repeat("d", 64),
		ContextDigest: request.ContextDigest,
		ExpiresAt:     request.ExpiresAt,
	}
	mock.ExpectBegin()
	expectIdentitySecurityIssuerScope(mock, request)
	mock.ExpectQuery("SELECT a1_cancel_scoped_identity_security_mutation_ticket").
		WithArgs(
			request.OrganizationID,
			request.ProjectID,
			request.AccountID,
			request.ActorID,
			request.SessionID,
			request.Operation,
			request.IdempotencyKey,
			request.ContextDigest,
			issued.TicketID,
			issued.ReceiptID,
		).
		WillReturnRows(sqlmock.NewRows([]string{"canceled"}).AddRow(true))
	mock.ExpectCommit()
	canceled, cancel := context.WithCancel(context.Background())
	cancel()
	if err := issuer.CancelIdentitySecurityMutationTicket(
		canceled,
		request,
		issued,
	); err != nil {
		t.Fatalf("cancel scoped ticket: %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("issuer cancel expectations: %v", err)
	}
}
