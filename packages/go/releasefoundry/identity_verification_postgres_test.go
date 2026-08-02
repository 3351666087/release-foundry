package releasefoundry

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"regexp"
	"strings"
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
	postgresVerificationSessionUUID    = "66666666-6666-4666-8666-666666666666"
	postgresVerificationCredentialUUID = "77777777-7777-4777-8777-777777777777"
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

func TestPostgresIdentityVerificationStoreCreateUsesSealedDeliveryMigrationFunction(t *testing.T) {
	t.Parallel()

	db, mock, store := newPostgresVerificationMock(t)
	defer db.Close()
	challenge := validPostgresVerificationChallenge()

	expectPostgresVerificationScope(mock)
	mock.ExpectQuery("FROM a1_issue_identity_verification_challenge_with_delivery").
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
			"vault:identity-delivery/postgres-1",
			sqlmock.AnyArg(),
		).
		WillReturnRows(sqlmock.NewRows(
			[]string{"challenge_id", "accepted", "retry_after_seconds"},
		).AddRow(postgresVerificationChallengeUUID, true, 0))
	mock.ExpectCommit()

	if err := store.CreateIdentityVerificationChallengeWithDelivery(
		context.Background(), challenge, time.Minute,
		postgresVerificationChallengeUUID, "vault:identity-delivery/postgres-1",
	); err != nil {
		t.Fatalf("create challenge: %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityVerificationChallengePrincipalScopeByPurpose(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name              string
		purpose           IdentityVerificationPurpose
		accountID         string
		wantPrincipalID   string
		wantDatabaseValue string
	}{
		{
			name:              "registration is accountless",
			purpose:           IdentityVerificationRegistration,
			wantPrincipalID:   "",
			wantDatabaseValue: "registration",
		},
		{
			name:              "login may be accountless",
			purpose:           IdentityVerificationLogin,
			wantPrincipalID:   "",
			wantDatabaseValue: "login",
		},
		{
			name:              "binding is account bound",
			purpose:           IdentityVerificationBinding,
			accountID:         postgresVerificationPrincipalID,
			wantPrincipalID:   postgresVerificationPrincipalID,
			wantDatabaseValue: "credential_binding",
		},
		{
			name:              "recovery is account bound",
			purpose:           IdentityVerificationRecovery,
			accountID:         postgresVerificationPrincipalID,
			wantPrincipalID:   postgresVerificationPrincipalID,
			wantDatabaseValue: "account_recovery",
		},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			db, mock, store := newPostgresVerificationMock(t)
			defer db.Close()
			challenge := validPostgresVerificationChallenge()
			challenge.Purpose = test.purpose
			challenge.AccountID = test.accountID

			expectPostgresVerificationScope(mock)
			mock.ExpectQuery("FROM a1_issue_identity_verification_challenge_with_delivery").
				WithArgs(
					postgresVerificationOrganizationID,
					postgresVerificationProjectID,
					test.wantPrincipalID,
					"email",
					test.wantDatabaseValue,
					challenge.IdentifierDigest,
					sqlmock.AnyArg(),
					challenge.CodeDigest,
					sqlmock.AnyArg(),
					challenge.ExpiresAt,
					challenge.AttemptCap,
					60,
					sqlmock.AnyArg(),
					"vault:identity-delivery/principal-scope",
					sqlmock.AnyArg(),
				).
				WillReturnRows(sqlmock.NewRows(
					[]string{"challenge_id", "accepted", "retry_after_seconds"},
				).AddRow(postgresVerificationChallengeUUID, true, 0))
			mock.ExpectCommit()

			if err := store.CreateIdentityVerificationChallengeWithDelivery(
				context.Background(),
				challenge,
				time.Minute,
				postgresVerificationChallengeUUID,
				"vault:identity-delivery/principal-scope",
			); err != nil {
				t.Fatalf("create challenge: %v", err)
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestPostgresIdentityVerificationStoreRejectsUnsealedOrInvalidDeliveryCreation(t *testing.T) {
	t.Parallel()
	db, mock, store := newPostgresVerificationMock(t)
	defer db.Close()
	challenge := validPostgresVerificationChallenge()
	if err := store.CreateIdentityVerificationChallenge(
		context.Background(), challenge, time.Minute,
	); verificationErrorCode(err) != "verification_delivery_seal_required" {
		t.Fatalf("unsealed creation did not fail closed: %v", err)
	}

	expectPostgresVerificationScope(mock)
	mock.ExpectQuery("a1_issue_identity_verification_challenge_with_delivery").
		WillReturnRows(sqlmock.NewRows(
			[]string{"challenge_id", "accepted", "retry_after_seconds"},
		).AddRow("not-a-database-uuid", true, 0))
	mock.ExpectRollback()
	err := store.CreateIdentityVerificationChallengeWithDelivery(
		context.Background(), challenge, time.Minute,
		postgresVerificationChallengeUUID, "vault:identity-delivery/postgres-1",
	)
	if verificationErrorCode(err) != "verification_store_unavailable" {
		t.Fatalf("invalid database challenge id was accepted: %v", err)
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
	mock.ExpectQuery("FROM a1_issue_identity_verification_challenge_with_delivery").
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
			"vault:identity-delivery/postgres-1",
			sqlmock.AnyArg(),
		).
		WillReturnRows(sqlmock.NewRows(
			[]string{"challenge_id", "accepted", "retry_after_seconds"},
		).AddRow(nil, false, 42))
	mock.ExpectCommit()

	err := store.CreateIdentityVerificationChallengeWithDelivery(
		context.Background(), challenge, time.Minute,
		postgresVerificationChallengeUUID, "vault:identity-delivery/postgres-1",
	)
	if verificationErrorCode(err) != "verification_resend_cooldown" {
		t.Fatalf("expected cooldown error, got %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityVerificationStoreMarksCommitOutcomeUnknown(t *testing.T) {
	t.Parallel()
	db, mock, store := newPostgresVerificationMock(t)
	defer db.Close()
	expectPostgresVerificationScope(mock)
	mock.ExpectQuery("a1_issue_identity_verification_challenge_with_delivery").
		WillReturnRows(sqlmock.NewRows(
			[]string{"challenge_id", "accepted", "retry_after_seconds"},
		).AddRow(postgresVerificationChallengeUUID, true, 0))
	mock.ExpectCommit().WillReturnError(errors.New("synthetic commit result unavailable"))
	err := store.CreateIdentityVerificationChallengeWithDelivery(
		context.Background(), validPostgresVerificationChallenge(), time.Minute,
		postgresVerificationChallengeUUID, "vault:identity-delivery/postgres-1",
	)
	if !errors.Is(err, ErrIdentityVerificationDeliveryCommitUnknown) {
		t.Fatalf("commit ambiguity was not preserved: %v", err)
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

	err := store.CreateIdentityVerificationChallengeWithDelivery(
		context.Background(), challenge, time.Minute,
		postgresVerificationChallengeUUID, "vault:identity-delivery/postgres-1",
	)
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

	err := store.CreateIdentityVerificationChallengeWithDelivery(
		ctx, validPostgresVerificationChallenge(), time.Minute,
		postgresVerificationChallengeUUID, "vault:identity-delivery/postgres-1",
	)
	if verificationErrorCode(err) != "verification_store_unavailable" {
		t.Fatalf("expected safe deadline error, got %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityVerificationBindingUsesAuthorizedAuthority(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 14, 9, 0, 0, 0, time.UTC)
	db, mock, store := newPostgresVerificationMock(t)
	defer db.Close()
	coordinator, err := NewPostgresIdentityVerificationTransactionCoordinator(store)
	if err != nil {
		t.Fatal(err)
	}
	command := validPostgresSessionCompletionCommand(now, IdentityVerificationBinding)
	command.ActorID = command.AccountID
	command.SessionDigest = strings.Repeat("c", 64)
	command.MutationTicketID = strings.Repeat("d", 64)
	command.StepUpReceiptID = strings.Repeat("e", 64)

	expectPostgresVerificationScope(mock)
	metadata := `{"source":"go_identity_verification_transaction_coordinator"}`
	mock.ExpectQuery("FROM a1_verify_identity_verification_attempt").
		WillReturnRows(sqlmock.NewRows([]string{
			"outcome_code", "challenge_id", "receipt_id", "principal_id",
			"channel", "purpose", "attempts_remaining",
		}).AddRow(
			"verified",
			postgresVerificationChallengeUUID,
			postgresVerificationReceiptUUID,
			postgresVerificationPrincipalID,
			"email",
			"credential_binding",
			3,
		))
	mock.ExpectQuery("SELECT a1_bind_verified_identity_credential_authorized").
		WithArgs(
			postgresVerificationOrganizationID,
			postgresVerificationProjectID,
			sqlmock.AnyArg(),
			command.AccountID,
			command.SessionDigest,
			command.MutationTicketID,
			command.StepUpReceiptID,
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			metadata,
		).
		WillReturnRows(sqlmock.NewRows([]string{"credential_id"}).AddRow(postgresVerificationChallengeUUID))
	mock.ExpectCommit()

	result, err := coordinator.CompleteIdentityVerification(context.Background(), command)
	if err != nil {
		t.Fatalf("complete authorized binding: %v", err)
	}
	if result.Account.AccountID != command.AccountID ||
		result.Credential.CredentialID != postgresVerificationChallengeUUID {
		t.Fatalf("unexpected binding result: %#v", result)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityVerificationBindingRejectsMissingTrustedAuthorizationBeforeSQL(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 14, 9, 0, 0, 0, time.UTC)
	tests := []struct {
		name   string
		mutate func(*IdentityVerificationCompletionCommand)
	}{
		{name: "actor", mutate: func(command *IdentityVerificationCompletionCommand) {
			command.ActorID = ""
		}},
		{name: "session digest", mutate: func(command *IdentityVerificationCompletionCommand) {
			command.SessionDigest = ""
		}},
		{name: "mutation ticket", mutate: func(command *IdentityVerificationCompletionCommand) {
			command.MutationTicketID = ""
		}},
		{name: "step-up receipt", mutate: func(command *IdentityVerificationCompletionCommand) {
			command.StepUpReceiptID = ""
		}},
	}
	for _, testCase := range tests {
		t.Run(testCase.name, func(t *testing.T) {
			db, mock, store := newPostgresVerificationMock(t)
			defer db.Close()
			coordinator, err := NewPostgresIdentityVerificationTransactionCoordinator(store)
			if err != nil {
				t.Fatal(err)
			}
			command := validPostgresSessionCompletionCommand(now, IdentityVerificationBinding)
			command.ActorID = command.AccountID
			command.SessionDigest = strings.Repeat("c", 64)
			command.MutationTicketID = strings.Repeat("d", 64)
			command.StepUpReceiptID = strings.Repeat("e", 64)
			testCase.mutate(&command)

			_, err = coordinator.CompleteIdentityVerification(context.Background(), command)
			if verificationErrorCode(err) != "credential_binding_authorization_required" {
				t.Fatalf("missing %s returned %v", testCase.name, err)
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestPostgresIdentityVerificationRegistrationUsesAccountlessReceiptAndCanonicalSessionResult(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 23, 9, 0, 0, 0, time.UTC)
	sessionKey := bytes.Repeat([]byte{0x19}, 32)
	accessNonce := bytes.Repeat([]byte{0x2b}, identitySessionNonceBytes)
	refreshNonce := bytes.Repeat([]byte{0x3c}, identitySessionNonceBytes)
	expectedBearer := identitySessionBearerPrefix + ".2026-07." +
		base64.RawURLEncoding.EncodeToString(accessNonce)
	expectedRefreshBearer := identityRefreshBearerPrefix + ".2026-07." +
		base64.RawURLEncoding.EncodeToString(refreshNonce)
	expectedSessionDigest := identitySessionHMAC(sessionKey, expectedBearer)
	expectedRefreshDigest := identitySessionHMAC(sessionKey, expectedRefreshBearer)
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	productionStore, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB: db, SessionKey: sessionKey, SessionKeyVersion: "2026-07",
		Random: bytes.NewReader(append(accessNonce, refreshNonce...)),
	})
	if err != nil {
		db.Close()
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = productionStore.Close() })
	verificationStore, err := productionStore.NewIdentityVerificationStore(
		postgresVerificationStoreOptions(db),
	)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(verificationStore.Close)
	coordinator, err := productionStore.NewIdentityVerificationTransactionCoordinator(
		verificationStore,
	)
	if err != nil {
		t.Fatal(err)
	}
	vault := &recordingIdentityDeliveryVault{}
	service, err := NewIdentityVerificationService(IdentityVerificationServiceOptions{
		Store: verificationStore, Sender: &countingIdentityVerificationSender{},
		DeliveryVaultSealer: vault, DeliveryVaultDeleter: vault,
		TransactionCoordinator: coordinator,
		Now:                    func() time.Time { return now },
		Random:                 bytes.NewReader(bytes.Repeat([]byte{0x41}, 1024)),
		DigestKey:              postgresVerificationDigestKey,
		TTL:                    5 * time.Minute,
		AttemptCap:             3,
		ResendCooldown:         time.Minute,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(service.Close)
	request := IdentityVerificationCompleteRequest{
		ChallengeID: "ivc_postgres_registration_01",
		Code:        "123456",
		Channel:     IdentityVerificationEmail,
		Identifier:  "registration@example.cn",
		Purpose:     IdentityVerificationRegistration,
		TenantID:    postgresVerificationOrganizationID,
		DisplayName: "Registration Account",
	}
	if _, err := service.Complete(
		context.Background(),
		request,
	); verificationErrorCode(err) != "session_issuance_required" {
		t.Fatalf("public registration completion created or exposed a production session: %v", err)
	}

	expectPostgresVerificationScope(mock)
	metadata := `{"source":"go_identity_verification_transaction_coordinator"}`
	mock.ExpectQuery("FROM a1_verify_identity_verification_attempt").
		WithArgs(
			postgresVerificationOrganizationID,
			postgresVerificationProjectID,
			sqlmock.AnyArg(),
			service.digest("code", request.ChallengeID, request.Code),
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			metadata,
		).
		WillReturnRows(sqlmock.NewRows([]string{
			"outcome_code", "challenge_id", "receipt_id", "principal_id",
			"channel", "purpose", "attempts_remaining",
		}).AddRow(
			"verified",
			postgresVerificationChallengeUUID,
			postgresVerificationReceiptUUID,
			nil,
			"email",
			"registration",
			3,
		))
	mock.ExpectQuery("FROM a1_register_with_verified_identity_with_refresh").
		WithArgs(
			postgresVerificationOrganizationID,
			postgresVerificationProjectID,
			sqlmock.AnyArg(),
			expectedSessionDigest,
			expectedRefreshDigest,
			sqlmock.AnyArg(),
			now.Add(24*time.Hour),
			now.Add(30*24*time.Hour),
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			request.DisplayName,
			metadata,
		).
		WillReturnRows(sqlmock.NewRows(
			[]string{"session_id", "principal_id", "credential_id"},
		).AddRow(
			postgresVerificationSessionUUID,
			postgresVerificationPrincipalID,
			postgresVerificationCredentialUUID,
		))
	mock.ExpectCommit()

	result, issuance, err := service.CompleteAndIssueSession(
		context.Background(),
		request,
	)
	if err != nil {
		t.Fatalf("issue registration session: %v", err)
	}
	if result.Account.AccountID != postgresVerificationPrincipalID ||
		result.Account.DisplayName != request.DisplayName ||
		result.Credential.CredentialID != postgresVerificationCredentialUUID ||
		!result.Created ||
		issuance.SessionID() != postgresVerificationSessionUUID {
		t.Fatalf("unexpected registration result=%#v receipt=%v", result, issuance)
	}
	bearer, refreshBearer, err := issuance.TakeBearerTokens()
	if err != nil || bearer != expectedBearer ||
		refreshBearer != expectedRefreshBearer {
		t.Fatalf(
			"registration bearer handoff access_matched=%t refresh_matched=%t err=%v",
			bearer == expectedBearer,
			refreshBearer == expectedRefreshBearer,
			err,
		)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityVerificationAccountlessLoginReturnsCanonicalIdentityAndOneTimeBearer(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 11, 11, 0, 0, 0, time.UTC)
	sessionKey := bytes.Repeat([]byte{0x2a}, 32)
	accessNonce := bytes.Repeat([]byte{0x6b}, identitySessionNonceBytes)
	refreshNonce := bytes.Repeat([]byte{0x7c}, identitySessionNonceBytes)
	expectedBearer := identitySessionBearerPrefix + ".2026-07." +
		base64.RawURLEncoding.EncodeToString(accessNonce)
	expectedRefreshBearer := identityRefreshBearerPrefix + ".2026-07." +
		base64.RawURLEncoding.EncodeToString(refreshNonce)
	expectedSessionDigest := identitySessionHMAC(sessionKey, expectedBearer)
	expectedRefreshDigest := identitySessionHMAC(sessionKey, expectedRefreshBearer)
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	productionStore, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB: db, SessionKey: sessionKey, SessionKeyVersion: "2026-07",
		Random: bytes.NewReader(append(accessNonce, refreshNonce...)),
	})
	if err != nil {
		db.Close()
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = productionStore.Close() })
	verificationStore, err := productionStore.NewIdentityVerificationStore(
		postgresVerificationStoreOptions(db),
	)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(verificationStore.Close)
	coordinator, err := productionStore.NewIdentityVerificationTransactionCoordinator(verificationStore)
	if err != nil {
		t.Fatal(err)
	}
	vault := &recordingIdentityDeliveryVault{}
	service, err := NewIdentityVerificationService(IdentityVerificationServiceOptions{
		Store: verificationStore, Sender: &countingIdentityVerificationSender{},
		DeliveryVaultSealer: vault, DeliveryVaultDeleter: vault,
		TransactionCoordinator: coordinator,
		Now:                    func() time.Time { return now },
		Random:                 bytes.NewReader(bytes.Repeat([]byte{0x71}, 1024)),
		DigestKey:              postgresVerificationDigestKey,
		TTL:                    5 * time.Minute,
		AttemptCap:             3,
		ResendCooldown:         time.Minute,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(service.Close)
	request := IdentityVerificationCompleteRequest{
		ChallengeID: "ivc_postgres_session_01", Code: "123456",
		Channel: IdentityVerificationEmail, Identifier: "session@example.test",
		Purpose: IdentityVerificationLogin, TenantID: postgresVerificationOrganizationID,
	}
	if _, err := service.Complete(context.Background(), request); verificationErrorCode(err) != "session_issuance_required" {
		t.Fatalf("public completion created or exposed a production session: %v", err)
	}

	expectPostgresVerificationScope(mock)
	metadata := `{"source":"go_identity_verification_transaction_coordinator"}`
	mock.ExpectQuery("FROM a1_verify_identity_verification_attempt").
		WithArgs(
			postgresVerificationOrganizationID,
			postgresVerificationProjectID,
			sqlmock.AnyArg(),
			service.digest("code", request.ChallengeID, request.Code),
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			metadata,
		).
		WillReturnRows(sqlmock.NewRows([]string{
			"outcome_code", "challenge_id", "receipt_id", "principal_id",
			"channel", "purpose", "attempts_remaining",
		}).AddRow(
			"verified",
			postgresVerificationChallengeUUID,
			postgresVerificationReceiptUUID,
			postgresVerificationPrincipalID,
			"email",
			"login",
			3,
		))
	mock.ExpectQuery("FROM a1_login_with_verified_identity_with_refresh_result").
		WithArgs(
			postgresVerificationOrganizationID,
			postgresVerificationProjectID,
			sqlmock.AnyArg(),
			expectedSessionDigest,
			expectedRefreshDigest,
			sqlmock.AnyArg(),
			now.Add(24*time.Hour),
			now.Add(30*24*time.Hour),
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			metadata,
		).
		WillReturnRows(sqlmock.NewRows(
			[]string{"session_id", "principal_id", "credential_id"},
		).AddRow(
			postgresVerificationSessionUUID,
			postgresVerificationPrincipalID,
			postgresVerificationCredentialUUID,
		))
	mock.ExpectCommit()

	result, issuance, err := service.CompleteAndIssueSession(context.Background(), request)
	if err != nil {
		t.Fatalf("issue production session: %v", err)
	}
	if result.Account.AccountID != postgresVerificationPrincipalID ||
		result.Credential.CredentialID != postgresVerificationCredentialUUID ||
		issuance.SessionID() != postgresVerificationSessionUUID ||
		issuance.KeyVersion() != "2026-07" ||
		issuance.RefreshKeyVersion() != "2026-07" ||
		!issuance.ExpiresAt().Equal(now.Add(24*time.Hour)) ||
		!issuance.RefreshExpiresAt().Equal(now.Add(30*24*time.Hour)) {
		t.Fatalf("unexpected issuance: result=%#v receipt=%v", result, issuance)
	}
	encodedResult, err := json.Marshal(struct {
		Result   IdentityVerificationResultDTO  `json:"result"`
		Issuance IdentitySessionIssuanceReceipt `json:"issuance"`
	}{Result: result, Issuance: issuance})
	if err != nil {
		t.Fatal(err)
	}
	renderedReceipt := fmt.Sprintf("%v %#v", issuance, issuance)
	if strings.Contains(string(encodedResult), expectedBearer) ||
		strings.Contains(string(encodedResult), expectedRefreshBearer) ||
		strings.Contains(renderedReceipt, expectedBearer) ||
		strings.Contains(renderedReceipt, expectedRefreshBearer) {
		t.Fatal("raw bearer escaped through DTO, JSON, or receipt formatting")
	}
	bearer, refreshBearer, err := issuance.TakeBearerTokens()
	if err != nil || bearer != expectedBearer || refreshBearer != expectedRefreshBearer {
		t.Fatalf(
			"take bearer pair: access_matched=%t refresh_matched=%t err=%v",
			bearer == expectedBearer,
			refreshBearer == expectedRefreshBearer,
			err,
		)
	}
	if second, secondRefresh, err := issuance.TakeBearerTokens(); !errors.Is(err, ErrIdentitySessionBearerTaken) || second != "" || secondRefresh != "" {
		t.Fatalf(
			"one-time receipt returned bearer pair twice: access_nonempty=%t refresh_nonempty=%t err=%v",
			second != "",
			secondRefresh != "",
			err,
		)
	}

	mock.ExpectQuery("FROM a1_authenticate_identity_session_digest").
		WithArgs(expectedSessionDigest).
		WillReturnRows(sqlmock.NewRows(
			[]string{"account", "actor", "session", "tenant", "project", "user"},
		).AddRow(
			postgresVerificationPrincipalID,
			postgresVerificationPrincipalID,
			postgresVerificationSessionUUID,
			postgresVerificationOrganizationID,
			postgresVerificationProjectID,
			postgresVerificationPrincipalID,
		))
	httpRequest, _ := http.NewRequest(http.MethodGet, "https://api.example.test", nil)
	httpRequest.Header.Set("Authorization", "Bearer "+bearer)
	resolved, err := productionStore.ResolveIdentityHTTPSession(context.Background(), httpRequest)
	if err != nil || resolved.SessionID != postgresVerificationSessionUUID ||
		resolved.SessionDigest != expectedSessionDigest {
		t.Fatalf("resolve issued bearer: session=%#v err=%v", resolved, err)
	}
	refreshRequest, _ := http.NewRequest(http.MethodGet, "https://api.example.test", nil)
	refreshRequest.Header.Set("Authorization", "Bearer "+refreshBearer)
	if _, err := productionStore.ResolveIdentityHTTPSession(context.Background(), refreshRequest); err == nil {
		t.Fatal("refresh bearer authenticated as an access session")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityVerificationSessionMutationFailureRollsBackWithoutReceipt(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 11, 12, 0, 0, 0, time.UTC)
	sessionKey := bytes.Repeat([]byte{0x3a}, 32)
	accessNonce := bytes.Repeat([]byte{0x4b}, identitySessionNonceBytes)
	refreshNonce := bytes.Repeat([]byte{0x5c}, identitySessionNonceBytes)
	expectedBearer := identitySessionBearerPrefix + ".v9." +
		base64.RawURLEncoding.EncodeToString(accessNonce)
	expectedRefreshBearer := identityRefreshBearerPrefix + ".v9." +
		base64.RawURLEncoding.EncodeToString(refreshNonce)
	expectedSessionDigest := identitySessionHMAC(sessionKey, expectedBearer)
	expectedRefreshDigest := identitySessionHMAC(sessionKey, expectedRefreshBearer)
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	productionStore, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB: db, SessionKey: sessionKey, SessionKeyVersion: "v9",
		Random: bytes.NewReader(append(accessNonce, refreshNonce...)),
	})
	if err != nil {
		db.Close()
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = productionStore.Close() })
	verificationStore, err := productionStore.NewIdentityVerificationStore(
		postgresVerificationStoreOptions(db),
	)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(verificationStore.Close)
	coordinator, err := productionStore.NewIdentityVerificationTransactionCoordinator(verificationStore)
	if err != nil {
		t.Fatal(err)
	}
	command := validPostgresSessionCompletionCommand(now, IdentityVerificationRecovery)

	expectPostgresVerificationScope(mock)
	metadata := `{"source":"go_identity_verification_transaction_coordinator"}`
	mock.ExpectQuery("FROM a1_verify_identity_verification_attempt").
		WillReturnRows(sqlmock.NewRows([]string{
			"outcome_code", "challenge_id", "receipt_id", "principal_id",
			"channel", "purpose", "attempts_remaining",
		}).AddRow(
			"verified",
			postgresVerificationChallengeUUID,
			postgresVerificationReceiptUUID,
			postgresVerificationPrincipalID,
			"email",
			"account_recovery",
			3,
		))
	mock.ExpectQuery("FROM a1_recover_verified_identity_with_refresh_result").
		WithArgs(
			postgresVerificationOrganizationID,
			postgresVerificationProjectID,
			sqlmock.AnyArg(),
			expectedSessionDigest,
			expectedRefreshDigest,
			sqlmock.AnyArg(),
			command.SessionExpiresAt,
			command.RefreshExpiresAt,
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			metadata,
		).
		WillReturnError(errors.New("session insert rejected"))
	mock.ExpectRollback()

	result, issuance, err := coordinator.CompleteIdentityVerificationAndIssueSession(
		context.Background(), command,
	)
	if verificationErrorCode(err) != "verification_mutation_rejected" {
		t.Fatalf("unexpected mutation failure: %v", err)
	}
	if result.SchemaVersion != "" || result.ChallengeID != "" ||
		result.Account.AccountID != "" || issuance.SessionID() != "" {
		t.Fatalf("failed transaction returned identity or issuance: result=%#v receipt=%v", result, issuance)
	}
	if bearer, takeErr := issuance.TakeBearerToken(); !errors.Is(takeErr, ErrIdentitySessionBearerTaken) || bearer != "" {
		t.Fatalf("failed transaction exposed bearer: nonempty=%t err=%v", bearer != "", takeErr)
	}
	if strings.Contains(fmt.Sprintf("%v", issuance), expectedBearer) ||
		strings.Contains(fmt.Sprintf("%v", issuance), expectedRefreshBearer) {
		t.Fatal("failed transaction formatted the generated bearer")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityVerificationSessionIssuerFailureRollsBackVerifiedProof(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 11, 12, 30, 0, 0, time.UTC)
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	productionStore, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB: db, SessionKey: bytes.Repeat([]byte{0x4a}, 32),
		SessionKeyVersion: "v10", Random: bytes.NewReader(nil),
	})
	if err != nil {
		db.Close()
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = productionStore.Close() })
	verificationStore, err := productionStore.NewIdentityVerificationStore(
		postgresVerificationStoreOptions(db),
	)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(verificationStore.Close)
	coordinator, err := productionStore.NewIdentityVerificationTransactionCoordinator(verificationStore)
	if err != nil {
		t.Fatal(err)
	}
	command := validPostgresSessionCompletionCommand(now, IdentityVerificationLogin)

	expectPostgresVerificationScope(mock)
	mock.ExpectQuery("FROM a1_verify_identity_verification_attempt").
		WillReturnRows(sqlmock.NewRows([]string{
			"outcome_code", "challenge_id", "receipt_id", "principal_id",
			"channel", "purpose", "attempts_remaining",
		}).AddRow(
			"verified",
			postgresVerificationChallengeUUID,
			postgresVerificationReceiptUUID,
			postgresVerificationPrincipalID,
			"email",
			"login",
			3,
		))
	mock.ExpectRollback()

	result, issuance, err := coordinator.CompleteIdentityVerificationAndIssueSession(
		context.Background(), command,
	)
	if verificationErrorCode(err) != "verification_store_unavailable" {
		t.Fatalf("issuer failure was not mapped safely: %v", err)
	}
	if result.SchemaVersion != "" || result.Account.AccountID != "" || issuance.SessionID() != "" {
		t.Fatalf("issuer failure returned identity or issuance: result=%#v receipt=%v", result, issuance)
	}
	if _, takeErr := issuance.TakeBearerToken(); !errors.Is(takeErr, ErrIdentitySessionBearerTaken) {
		t.Fatalf("issuer failure returned a bearer receipt: %v", takeErr)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func validPostgresSessionCompletionCommand(
	now time.Time,
	purpose IdentityVerificationPurpose,
) IdentityVerificationCompletionCommand {
	return IdentityVerificationCompletionCommand{
		ChallengeID:         "ivc_postgres_session_rollback",
		CandidateCodeDigest: postgresVerificationDigestA,
		IdentifierDigest:    postgresVerificationDigestB,
		Channel:             IdentityVerificationEmail,
		CredentialKind:      IdentityCredentialEmail,
		Purpose:             purpose,
		TenantID:            postgresVerificationOrganizationID,
		AccountID:           postgresVerificationPrincipalID,
		VerifiedAt:          now,
		SessionExpiresAt:    now.Add(24 * time.Hour),
		RefreshExpiresAt:    now.Add(30 * 24 * time.Hour),
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
