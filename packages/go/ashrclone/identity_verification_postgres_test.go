package ashrclone

import (
	"bytes"
	"context"
	"database/sql"
	"errors"
	"regexp"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
)

const (
	postgresVerificationOrganizationID = "11111111-1111-4111-8111-111111111111"
	postgresVerificationProjectID      = "22222222-2222-4222-8222-222222222222"
	postgresVerificationPrincipalID    = "33333333-3333-4333-8333-333333333333"
	postgresVerificationChallengeUUID  = "44444444-4444-4444-8444-444444444444"
	postgresVerificationReceiptUUID    = "55555555-5555-4555-8555-555555555555"
	postgresVerificationDigestA        = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	postgresVerificationDigestB        = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
)

var postgresVerificationDigestKey = bytes.Repeat([]byte{0x5a}, 32)

func TestNewPostgresIdentityVerificationStoreRequiresScope(t *testing.T) {
	t.Parallel()

	if _, err := NewPostgresIdentityVerificationStore(nil); err == nil {
		t.Fatal("expected nil db rejection")
	}
	db, _, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if _, err := NewPostgresIdentityVerificationStore(db); err == nil {
		t.Fatal("expected unscoped constructor to fail closed")
	}

	base := postgresVerificationStoreOptions(db)
	tests := []PostgresIdentityVerificationStoreOptions{
		func() PostgresIdentityVerificationStoreOptions {
			value := base
			value.OrganizationID = "tenant_1"
			return value
		}(),
		func() PostgresIdentityVerificationStoreOptions {
			value := base
			value.ProjectID = "project_1"
			return value
		}(),
		func() PostgresIdentityVerificationStoreOptions {
			value := base
			value.PrincipalID = "principal_1"
			return value
		}(),
		func() PostgresIdentityVerificationStoreOptions {
			value := base
			value.DigestKey = []byte("short")
			return value
		}(),
		func() PostgresIdentityVerificationStoreOptions {
			value := base
			value.OperationTimeout = 31 * time.Second
			return value
		}(),
	}
	for index, options := range tests {
		if _, err := NewPostgresIdentityVerificationStoreWithOptions(options); err == nil {
			t.Fatalf("expected constructor case %d to fail", index)
		}
	}
}

func TestPostgresIdentityVerificationStoreCreateUsesMigrationFunction(t *testing.T) {
	t.Parallel()

	db, mock, store := newPostgresVerificationMock(t)
	defer db.Close()
	challenge := validPostgresVerificationChallenge()

	expectPostgresVerificationScope(mock)
	mock.ExpectQuery("FROM a1_issue_identity_verification_challenge").
		WithArgs(
			postgresVerificationOrganizationID,
			postgresVerificationProjectID,
			postgresVerificationPrincipalID,
			"email",
			"credential_binding",
			challenge.IdentifierDigest,
			sqlmock.AnyArg(),
			challenge.CodeDigest,
			sqlmock.AnyArg(),
			challenge.ExpiresAt,
			5,
			60,
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
		).
		WillReturnRows(sqlmock.NewRows(
			[]string{"challenge_id", "accepted", "retry_after_seconds"},
		).AddRow(postgresVerificationChallengeUUID, true, 0))
	mock.ExpectCommit()

	if err := store.CreateIdentityVerificationChallenge(
		context.Background(), challenge, time.Minute,
	); err != nil {
		t.Fatalf("create challenge: %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityVerificationStoreCreateMapsCooldown(t *testing.T) {
	t.Parallel()

	db, mock, store := newPostgresVerificationMock(t)
	defer db.Close()
	challenge := validPostgresVerificationChallenge()

	expectPostgresVerificationScope(mock)
	mock.ExpectQuery("FROM a1_issue_identity_verification_challenge").
		WithArgs(
			postgresVerificationOrganizationID,
			postgresVerificationProjectID,
			postgresVerificationPrincipalID,
			"email",
			"credential_binding",
			challenge.IdentifierDigest,
			sqlmock.AnyArg(),
			challenge.CodeDigest,
			sqlmock.AnyArg(),
			challenge.ExpiresAt,
			5,
			60,
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
		).
		WillReturnRows(sqlmock.NewRows(
			[]string{"challenge_id", "accepted", "retry_after_seconds"},
		).AddRow(nil, false, 42))
	mock.ExpectCommit()

	err := store.CreateIdentityVerificationChallenge(context.Background(), challenge, time.Minute)
	if verificationErrorCode(err) != "verification_resend_cooldown" {
		t.Fatalf("expected cooldown error, got %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityVerificationStoreCreateValidatesBeforeQuery(t *testing.T) {
	t.Parallel()

	db, mock, store := newPostgresVerificationMock(t)
	defer db.Close()
	challenge := validPostgresVerificationChallenge()
	challenge.AttemptCap = 11

	err := store.CreateIdentityVerificationChallenge(context.Background(), challenge, time.Minute)
	if verificationErrorCode(err) != "invalid_verification_challenge" {
		t.Fatalf("expected validation error, got %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityVerificationStoreVerifyConsumeSuccess(t *testing.T) {
	t.Parallel()

	db, mock, store := newPostgresVerificationMock(t)
	defer db.Close()
	challenge := validPostgresVerificationChallenge()
	requestDigest, err := store.RequestContextDigest(challenge)
	if err != nil {
		t.Fatal(err)
	}

	expectPostgresVerificationScope(mock)
	mock.ExpectQuery("FROM a1_verify_consume_identity_challenge").
		WithArgs(
			postgresVerificationOrganizationID,
			postgresVerificationProjectID,
			sqlmock.AnyArg(),
			challenge.CodeDigest,
			requestDigest,
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			`{"ip_class":"trusted"}`,
		).
		WillReturnRows(sqlmock.NewRows([]string{
			"outcome_code", "challenge_id", "receipt_id", "principal_id",
			"channel", "purpose", "attempts_remaining",
		}).AddRow(
			"consumed",
			postgresVerificationChallengeUUID,
			postgresVerificationReceiptUUID,
			postgresVerificationPrincipalID,
			"email",
			"credential_binding",
			5,
		))
	mock.ExpectCommit()

	receipt, err := store.VerifyConsumeIdentityVerificationChallenge(
		context.Background(),
		PostgresIdentityVerificationProof{
			ChallengeID:          challenge.ChallengeID,
			CandidateCodeDigest:  challenge.CodeDigest,
			RequestContextDigest: requestDigest,
			Metadata:             map[string]any{"ip_class": "trusted"},
		},
	)
	if err != nil {
		t.Fatalf("verify challenge: %v", err)
	}
	if receipt.ChallengeID != challenge.ChallengeID ||
		receipt.ReceiptID != postgresVerificationReceiptUUID ||
		receipt.PrincipalID != postgresVerificationPrincipalID ||
		receipt.Purpose != IdentityVerificationBinding ||
		receipt.AttemptsRemaining != 5 {
		t.Fatalf("unexpected receipt: %#v", receipt)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityVerificationStoreVerifyPersistsRejectedAttempt(t *testing.T) {
	t.Parallel()

	db, mock, store := newPostgresVerificationMock(t)
	defer db.Close()
	challenge := validPostgresVerificationChallenge()
	requestDigest, err := store.RequestContextDigest(challenge)
	if err != nil {
		t.Fatal(err)
	}

	expectPostgresVerificationScope(mock)
	mock.ExpectQuery("FROM a1_verify_consume_identity_challenge").
		WillReturnRows(sqlmock.NewRows([]string{
			"outcome_code", "challenge_id", "receipt_id", "principal_id",
			"channel", "purpose", "attempts_remaining",
		}).AddRow(
			"rejected",
			postgresVerificationChallengeUUID,
			nil,
			postgresVerificationPrincipalID,
			"email",
			"credential_binding",
			4,
		))
	mock.ExpectCommit()

	_, err = store.VerifyConsumeIdentityVerificationChallenge(
		context.Background(),
		PostgresIdentityVerificationProof{
			ChallengeID:          challenge.ChallengeID,
			CandidateCodeDigest:  postgresVerificationDigestA,
			RequestContextDigest: requestDigest,
		},
	)
	if verificationErrorCode(err) != "verification_rejected" {
		t.Fatalf("expected non-enumerating rejection, got %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityVerificationStoreDatabaseErrorIsPublicSafe(t *testing.T) {
	t.Parallel()

	db, mock, store := newPostgresVerificationMock(t)
	defer db.Close()
	challenge := validPostgresVerificationChallenge()
	requestDigest, err := store.RequestContextDigest(challenge)
	if err != nil {
		t.Fatal(err)
	}
	providerDetail := "pq: protected table detail"

	expectPostgresVerificationScope(mock)
	mock.ExpectQuery("FROM a1_verify_consume_identity_challenge").
		WillReturnError(errors.New(providerDetail))
	mock.ExpectRollback()

	_, err = store.VerifyConsumeIdentityVerificationChallenge(
		context.Background(),
		PostgresIdentityVerificationProof{
			ChallengeID:          challenge.ChallengeID,
			CandidateCodeDigest:  challenge.CodeDigest,
			RequestContextDigest: requestDigest,
		},
	)
	if verificationErrorCode(err) != "verification_store_unavailable" {
		t.Fatalf("expected safe store error, got %v", err)
	}
	if regexp.MustCompile(regexp.QuoteMeta(providerDetail)).MatchString(err.Error()) {
		t.Fatal("database detail escaped through public error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityVerificationStoreLegacyConsumeFailsClosed(t *testing.T) {
	t.Parallel()

	db, mock, store := newPostgresVerificationMock(t)
	defer db.Close()
	_, err := store.ConsumeIdentityVerificationChallenge(
		context.Background(),
		validPostgresVerificationChallenge().ChallengeID,
		func(IdentityVerificationChallenge) error { return nil },
	)
	if verificationErrorCode(err) != "verification_durable_proof_required" {
		t.Fatalf("expected durable proof requirement, got %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityVerificationStoreHonorsParentDeadline(t *testing.T) {
	t.Parallel()

	db, mock, store := newPostgresVerificationMock(t)
	defer db.Close()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	err := store.CreateIdentityVerificationChallenge(
		ctx, validPostgresVerificationChallenge(), time.Minute,
	)
	if verificationErrorCode(err) != "verification_store_unavailable" {
		t.Fatalf("expected safe deadline error, got %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func newPostgresVerificationMock(
	t *testing.T,
) (*sql.DB, sqlmock.Sqlmock, *PostgresIdentityVerificationStore) {
	t.Helper()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	store, err := NewPostgresIdentityVerificationStoreWithOptions(
		postgresVerificationStoreOptions(db),
	)
	if err != nil {
		db.Close()
		t.Fatal(err)
	}
	t.Cleanup(store.Close)
	return db, mock, store
}

func postgresVerificationStoreOptions(
	db *sql.DB,
) PostgresIdentityVerificationStoreOptions {
	return PostgresIdentityVerificationStoreOptions{
		DB:             db,
		OrganizationID: postgresVerificationOrganizationID,
		ProjectID:      postgresVerificationProjectID,
		PrincipalID:    postgresVerificationPrincipalID,
		DigestKey:      postgresVerificationDigestKey,
		Random:         bytes.NewReader(bytes.Repeat([]byte{0x7c}, 4096)),
	}
}

func validPostgresVerificationChallenge() IdentityVerificationChallenge {
	createdAt := time.Now().UTC().Truncate(time.Microsecond)
	return IdentityVerificationChallenge{
		ChallengeID:      "ivc_postgres_test_01",
		Channel:          IdentityVerificationEmail,
		IdentifierDigest: postgresVerificationDigestA,
		CodeDigest:       postgresVerificationDigestB,
		Purpose:          IdentityVerificationBinding,
		TenantID:         postgresVerificationOrganizationID,
		AccountID:        postgresVerificationPrincipalID,
		AttemptCap:       5,
		CreatedAt:        createdAt,
		ExpiresAt:        createdAt.Add(10 * time.Minute),
	}
}

func expectPostgresVerificationScope(mock sqlmock.Sqlmock) {
	mock.ExpectBegin()
	mock.ExpectExec("set_config\\('app.a1_organization_id'").
		WithArgs(postgresVerificationOrganizationID, postgresVerificationProjectID).
		WillReturnResult(sqlmock.NewResult(0, 1))
}
