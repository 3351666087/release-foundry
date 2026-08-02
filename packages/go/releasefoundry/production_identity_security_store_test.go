package releasefoundry

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/lib/pq"
)

const identitySecurityTestAccountID = "33333333-3333-4333-8333-333333333333"

func newProductionIdentitySecurityTestStore(
	t *testing.T,
	now time.Time,
) (*ProductionIdentityStore, sqlmock.Sqlmock) {
	t.Helper()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB: db, SessionKey: bytes.Repeat([]byte{0x71}, 32), Now: func() time.Time { return now },
		SQLTimeout: time.Second, StatementTimeout: 800 * time.Millisecond, LockTimeout: 200 * time.Millisecond,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { store.sessionTokens.close() })
	return store, mock
}

func expectIdentitySecurityTransaction(mock sqlmock.Sqlmock) {
	mock.ExpectBegin()
	mock.ExpectExec("SELECT set_config").WithArgs(
		"800ms", "200ms", identitySecurityTestAccountID,
	).
		WillReturnResult(sqlmock.NewResult(0, 1))
}

func TestProductionIdentitySecurityStoreProjectsPublicPosture(t *testing.T) {
	now := time.Date(2026, 7, 14, 8, 0, 0, 0, time.UTC)
	store, mock := newProductionIdentitySecurityTestStore(t, now)
	raw := `{
	  "password_status":"set",
	  "password_change_available":true,
	  "password_recovery_available":true,
	  "two_factor_status":"enabled",
	  "two_factor_optional":true,
	  "two_factor_recommended":true,
	  "recovery_codes_remaining":10,
	  "security_version":4,
	  "active_sessions":2
	}`
	expectIdentitySecurityTransaction(mock)
	mock.ExpectQuery("SELECT a1_project_account_security").
		WithArgs(identitySecurityTestAccountID).
		WillReturnRows(sqlmock.NewRows([]string{"posture"}).AddRow(raw))
	mock.ExpectCommit()

	posture, err := store.GetIdentitySecurityPosture(context.Background(), identitySecurityTestAccountID)
	if err != nil {
		t.Fatal(err)
	}
	if posture.PasswordStatus != "set" || posture.TwoFactorStatus != "enabled" ||
		!posture.TwoFactorOptional || !posture.TwoFactorRecommended ||
		posture.RecoveryCodesRemaining != 10 || posture.SecurityVersion != 4 ||
		posture.ActiveSessions != 2 {
		t.Fatalf("unexpected public posture: %#v", posture)
	}
	encoded, err := json.Marshal(posture)
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range []string{"secret_ref", "secret_digest", "receipt_digest", "recovery_batch_digest"} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatalf("public posture exposed %s: %s", forbidden, encoded)
		}
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestProductionIdentitySecurityStoreResolvesPublicTicketEnvelope(t *testing.T) {
	now := time.Date(2026, 7, 14, 8, 0, 0, 0, time.UTC)
	store, mock := newProductionIdentitySecurityTestStore(t, now)
	ticketID := strings.Repeat("a", 64)
	stepUpID := strings.Repeat("b", 64)
	raw := `{
	  "ticket_id":"` + ticketID + `",
	  "account_id":"` + identitySecurityTestAccountID + `",
	  "operation":"password_enroll",
	  "step_up_receipt_id":"` + stepUpID + `",
	  "expires_at":"2026-07-14T08:05:00Z"
	}`
	expectIdentitySecurityTransaction(mock)
	mock.ExpectQuery("SELECT a1_resolve_identity_security_mutation_ticket").
		WithArgs(ticketID, stepUpID, "password_enroll", identitySecurityTestAccountID, now).
		WillReturnRows(sqlmock.NewRows([]string{"ticket"}).AddRow(raw))
	mock.ExpectCommit()

	ticket, err := store.ResolveIdentitySecurityMutationTicket(
		context.Background(), identitySecurityTestAccountID,
		ticketID, stepUpID, "password_enroll",
	)
	if err != nil {
		t.Fatal(err)
	}
	if ticket.TicketID != ticketID || ticket.AccountID != identitySecurityTestAccountID ||
		ticket.Operation != "password_enroll" || ticket.ReceiptDigest != stepUpID ||
		!ticket.ExpiresAt.Equal(now.Add(5*time.Minute)) {
		t.Fatalf("unexpected public ticket envelope: %#v", ticket)
	}
	encoded, err := json.Marshal(ticket)
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range []string{"vault://", "secret_ref", "secret_digest", "context_digest", "recovery_batch_digest"} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatalf("ticket envelope exposed trusted material %q: %s", forbidden, encoded)
		}
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestProductionIdentitySecurityStoreResolvesCredentialBindTicket(t *testing.T) {
	now := time.Date(2026, 7, 14, 8, 0, 0, 0, time.UTC)
	store, mock := newProductionIdentitySecurityTestStore(t, now)
	ticketID := strings.Repeat("a", 64)
	stepUpID := strings.Repeat("b", 64)
	raw := `{
	  "ticket_id":"` + ticketID + `",
	  "account_id":"` + identitySecurityTestAccountID + `",
	  "operation":"credential_bind",
	  "step_up_receipt_id":"` + stepUpID + `",
	  "expires_at":"2026-07-14T08:05:00Z"
	}`
	expectIdentitySecurityTransaction(mock)
	mock.ExpectQuery("SELECT a1_resolve_identity_security_mutation_ticket").
		WithArgs(ticketID, stepUpID, "credential_bind", identitySecurityTestAccountID, now).
		WillReturnRows(sqlmock.NewRows([]string{"ticket"}).AddRow(raw))
	mock.ExpectCommit()

	ticket, err := store.ResolveIdentitySecurityMutationTicket(
		context.Background(), identitySecurityTestAccountID,
		ticketID, stepUpID, "credential_bind",
	)
	if err != nil {
		t.Fatal(err)
	}
	if ticket.Operation != "credential_bind" || ticket.AccountID != identitySecurityTestAccountID {
		t.Fatalf("unexpected credential-bind ticket: %#v", ticket)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestProductionIdentitySecurityStoreRejectsCredentialBindInGenericExecutor(t *testing.T) {
	now := time.Date(2026, 7, 14, 8, 0, 0, 0, time.UTC)
	store, mock := newProductionIdentitySecurityTestStore(t, now)
	_, err := store.MutateIdentitySecurity(context.Background(), IdentitySecurityMutation{
		AccountID:      identitySecurityTestAccountID,
		ActorID:        identitySecurityTestAccountID,
		SessionID:      "security-session",
		Operation:      "credential_bind",
		IdempotencyKey: "security-idempotency-key",
		Ticket: IdentitySecurityMutationTicket{
			TicketID:      strings.Repeat("a", 64),
			AccountID:     identitySecurityTestAccountID,
			Operation:     "credential_bind",
			ReceiptDigest: strings.Repeat("b", 64),
			ExpiresAt:     now.Add(time.Minute),
		},
	})
	if !errors.Is(err, ErrIdentitySecurityRejected) {
		t.Fatalf("credential_bind entered generic executor: %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestProductionIdentitySecurityStoreRoutesAtomicMigration018Authority(t *testing.T) {
	now := time.Date(2026, 7, 14, 8, 0, 0, 0, time.UTC)
	baseTicket := IdentitySecurityMutationTicket{
		TicketID:      strings.Repeat("a", 64),
		AccountID:     identitySecurityTestAccountID,
		ReceiptDigest: strings.Repeat("b", 64),
		ExpiresAt:     now.Add(time.Minute),
	}
	tests := []struct {
		operation  string
		resultJSON string
	}{
		{
			operation:  "password_enroll",
			resultJSON: `{"password_status":"set","security_version":2,"sessions_revoked":1,"reauthentication_required":true}`,
		},
		{
			operation:  "mfa_enroll",
			resultJSON: `{"two_factor_status":"pending","confirmation_required":true,"security_version":3,"sessions_revoked":0}`,
		},
		{
			operation:  "mfa_confirm",
			resultJSON: `{"two_factor_status":"enabled","recovery_codes_remaining":10,"security_version":4,"sessions_revoked":1,"reauthentication_required":true}`,
		},
	}
	for _, testCase := range tests {
		t.Run(testCase.operation, func(t *testing.T) {
			store, mock := newProductionIdentitySecurityTestStore(t, now)
			ticket := baseTicket
			ticket.Operation = testCase.operation
			mutation := IdentitySecurityMutation{
				AccountID: identitySecurityTestAccountID, ActorID: identitySecurityTestAccountID,
				SessionID: "security-session", Operation: testCase.operation,
				IdempotencyKey: "security-idempotency-key", Ticket: ticket,
			}
			expectIdentitySecurityTransaction(mock)
			mock.ExpectQuery("SELECT a1_execute_identity_security_mutation").
				WithArgs(ticket.TicketID, mutation.IdempotencyKey,
					identitySecurityRequestFingerprint(mutation),
					identitySecurityTestAccountID).
				WillReturnRows(sqlmock.NewRows([]string{"result"}).AddRow(testCase.resultJSON))
			mock.ExpectCommit()

			result, err := store.MutateIdentitySecurity(context.Background(), mutation)
			if err != nil {
				t.Fatal(err)
			}
			encoded, err := json.Marshal(result)
			if err != nil {
				t.Fatal(err)
			}
			if strings.Contains(string(encoded), "vault://") || strings.Contains(string(encoded), ticket.ReceiptDigest) {
				t.Fatalf("mutation result exposed trusted material: %s", encoded)
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestProductionIdentitySecurityStoreRejectsInvalidTrustedTicketBeforeSQL(t *testing.T) {
	now := time.Date(2026, 7, 14, 8, 0, 0, 0, time.UTC)
	store, mock := newProductionIdentitySecurityTestStore(t, now)
	_, err := store.MutateIdentitySecurity(context.Background(), IdentitySecurityMutation{
		AccountID: identitySecurityTestAccountID, ActorID: identitySecurityTestAccountID,
		Operation: "password_enroll", IdempotencyKey: "idem",
		Ticket: IdentitySecurityMutationTicket{
			TicketID: strings.Repeat("a", 64), AccountID: identitySecurityTestAccountID,
			Operation: "password_enroll", ReceiptDigest: strings.Repeat("b", 64),
			ExpiresAt: now.Add(time.Minute),
		},
	})
	if !errors.Is(err, ErrIdentitySecurityRejected) {
		t.Fatalf("invalid trusted ticket returned %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestProductionIdentitySecurityStoreClassifiesDatabaseErrorsSafely(t *testing.T) {
	for name, testCase := range map[string]struct {
		databaseError error
		want          error
	}{
		"authorization": {databaseError: &pq.Error{Code: "42501"}, want: ErrIdentitySecurityRejected},
		"domain state":  {databaseError: &pq.Error{Code: "55000"}, want: ErrIdentitySecurityRejected},
		"serialization": {databaseError: &pq.Error{Code: "40001"}, want: ErrIdentitySecurityUnavailable},
		"deadlock":      {databaseError: &pq.Error{Code: "40P01"}, want: ErrIdentitySecurityUnavailable},
		"lock timeout":  {databaseError: &pq.Error{Code: "55P03"}, want: ErrIdentitySecurityUnavailable},
		"connection":    {databaseError: &pq.Error{Code: "08006"}, want: ErrIdentitySecurityUnavailable},
		"private":       {databaseError: errors.New("private database detail"), want: ErrIdentitySecurityUnavailable},
	} {
		t.Run(name, func(t *testing.T) {
			got := identitySecurityDatabaseError(testCase.databaseError)
			if !errors.Is(got, testCase.want) || strings.Contains(got.Error(), "private database detail") {
				t.Fatalf("unsafe database error classification: %v", got)
			}
		})
	}
}
