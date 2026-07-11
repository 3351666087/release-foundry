package ashrclone

import (
	"context"
	cryptorand "crypto/rand"
	"database/sql"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"regexp"
	"sync"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/lib/pq"
)

const (
	postgresDeliveryOrganizationID = "11111111-1111-4111-8111-111111111111"
	postgresDeliveryProjectID      = "22222222-2222-4222-8222-222222222222"
	postgresDeliveryTaskID         = "33333333-3333-4333-8333-333333333333"
	postgresDeliveryChallengeID    = "44444444-4444-4444-8444-444444444444"
	postgresDeliveryAuditID        = "55555555-5555-4555-8555-555555555555"
)

func TestNewPostgresIdentityDeliveryOutboxStoreRejectsNilDB(t *testing.T) {
	t.Parallel()
	if _, err := NewPostgresIdentityDeliveryOutboxStore(nil); err == nil {
		t.Fatal("nil db was accepted")
	}
}

func TestPostgresIdentityDeliveryClaimUsesScopedParameterizedFunction(t *testing.T) {
	t.Parallel()
	db, mock, store := newPostgresIdentityDeliveryMock(t)
	defer db.Close()

	now := time.Date(2026, 7, 11, 9, 0, 0, 0, time.UTC)
	expiresAt := now.Add(10 * time.Minute)
	leaseExpiresAt := now.Add(1500 * time.Millisecond)
	expectPostgresIdentityDeliveryScope(mock, postgresDeliveryOrganizationID, postgresDeliveryProjectID)
	mock.ExpectQuery(regexp.QuoteMeta("FROM a1_claim_identity_delivery_outbox(")).
		WithArgs(
			postgresDeliveryOrganizationID,
			postgresDeliveryProjectID,
			"worker-a",
			7,
			int64(1500),
			now,
		).
		WillReturnRows(sqlmock.NewRows([]string{
			"outbox_id", "organization_id", "project_id", "challenge_id",
			"channel", "purpose", "opaque_ref", "challenge_expires_at",
			"attempt_count", "max_attempts", "provider_idempotency_key",
			"lease_owner", "lease_generation", "lease_expires_at",
		}).AddRow(
			postgresDeliveryTaskID,
			postgresDeliveryOrganizationID,
			postgresDeliveryProjectID,
			postgresDeliveryChallengeID,
			"email",
			"credential_binding",
			"vault:identity-delivery/task-1",
			expiresAt,
			1,
			8,
			"identity-delivery:44444444-4444-4444-8444-444444444444:0",
			"worker-a",
			int64(1),
			leaseExpiresAt,
		))
	mock.ExpectCommit()

	tasks, err := store.ClaimIdentityDeliveries(
		context.Background(),
		postgresDeliveryOrganizationID,
		postgresDeliveryProjectID,
		"worker-a",
		7,
		1500*time.Millisecond,
		now,
	)
	if err != nil {
		t.Fatalf("claim: %v", err)
	}
	if len(tasks) != 1 {
		t.Fatalf("expected one task, got %#v", tasks)
	}
	task := tasks[0]
	if task.ID != postgresDeliveryTaskID ||
		task.TenantID != postgresDeliveryOrganizationID ||
		task.ProjectID != postgresDeliveryProjectID ||
		task.ChallengeID != postgresDeliveryChallengeID ||
		task.OpaqueRef != "vault:identity-delivery/task-1" ||
		task.Purpose != IdentityVerificationBinding ||
		task.ProviderIdempotencyKey != "identity-delivery:44444444-4444-4444-8444-444444444444:0" ||
		task.Attempt != 1 || task.MaxAttempts != 8 ||
		task.LeaseGeneration != 1 ||
		!task.ChallengeExpiresAt.Equal(expiresAt) ||
		!task.LeaseExpiresAt.Equal(leaseExpiresAt) {
		t.Fatalf("claim did not preserve durable fields: %#v", task)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityDeliveryClaimRejectsInvalidProviderKey(t *testing.T) {
	t.Parallel()
	db, mock, store := newPostgresIdentityDeliveryMock(t)
	defer db.Close()

	now := time.Date(2026, 7, 11, 9, 0, 0, 0, time.UTC)
	expectPostgresIdentityDeliveryScope(mock, postgresDeliveryOrganizationID, postgresDeliveryProjectID)
	mock.ExpectQuery("a1_claim_identity_delivery_outbox").
		WillReturnRows(sqlmock.NewRows([]string{
			"outbox_id", "organization_id", "project_id", "challenge_id",
			"channel", "purpose", "opaque_ref", "challenge_expires_at",
			"attempt_count", "max_attempts", "provider_idempotency_key",
			"lease_owner", "lease_generation", "lease_expires_at",
		}).AddRow(
			postgresDeliveryTaskID,
			postgresDeliveryOrganizationID,
			postgresDeliveryProjectID,
			postgresDeliveryChallengeID,
			"phone",
			"account_recovery",
			"opaque-ref:identity-delivery/task-1",
			now.Add(time.Minute),
			1,
			8,
			"bad key with spaces",
			"worker-a",
			int64(1),
			now.Add(30*time.Second),
		))
	mock.ExpectRollback()

	_, err := store.ClaimIdentityDeliveries(
		context.Background(), postgresDeliveryOrganizationID,
		postgresDeliveryProjectID, "worker-a", 1, 30*time.Second, now,
	)
	if err == nil {
		t.Fatal("invalid provider idempotency key was accepted")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityDeliveryHeartbeatPreservesFence(t *testing.T) {
	t.Parallel()
	db, mock, store := newPostgresIdentityDeliveryMock(t)
	defer db.Close()

	now := time.Date(2026, 7, 11, 9, 0, 10, 0, time.UTC)
	task := validPostgresIdentityDeliveryTask(now)
	renewedUntil := now.Add(45 * time.Second)
	expectPostgresIdentityDeliveryScope(mock, task.TenantID, task.ProjectID)
	mock.ExpectQuery("a1_heartbeat_identity_delivery_outbox").
		WithArgs(
			task.TenantID,
			task.ProjectID,
			task.ID,
			task.LeaseOwner,
			task.LeaseGeneration,
			int64(45000),
			now,
		).
		WillReturnRows(sqlmock.NewRows([]string{"lease_expires_at"}).AddRow(renewedUntil))
	mock.ExpectCommit()

	renewed, err := store.HeartbeatIdentityDelivery(
		context.Background(), task, 45*time.Second, now,
	)
	if err != nil {
		t.Fatalf("heartbeat: %v", err)
	}
	if !renewed.LeaseExpiresAt.Equal(renewedUntil) ||
		renewed.LeaseGeneration != task.LeaseGeneration ||
		renewed.LeaseOwner != task.LeaseOwner || renewed.ID != task.ID {
		t.Fatalf("heartbeat changed the task fence: before=%#v after=%#v", task, renewed)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityDeliveryCompleteMapsLostGeneration(t *testing.T) {
	t.Parallel()
	db, mock, store := newPostgresIdentityDeliveryMock(t)
	defer db.Close()

	now := time.Date(2026, 7, 11, 9, 0, 10, 0, time.UTC)
	task := validPostgresIdentityDeliveryTask(now)
	acceptance := IdentityDeliveryProviderAcceptance{
		Reference: "provider-ref:relay-1", AcceptedAt: now,
	}
	expectPostgresIdentityDeliveryScope(mock, task.TenantID, task.ProjectID)
	mock.ExpectQuery("a1_complete_identity_delivery_outbox").
		WithArgs(
			task.TenantID,
			task.ProjectID,
			task.ID,
			task.LeaseOwner,
			task.LeaseGeneration,
			acceptance.Reference,
			acceptance.AcceptedAt,
			now,
		).
		WillReturnError(&pq.Error{
			Code:    pq.ErrorCode(postgresIdentityDeliveryLeaseLostSQLState),
			Message: "identity delivery lease lost",
		})
	mock.ExpectRollback()

	err := store.CompleteIdentityDelivery(context.Background(), task, acceptance, now)
	if !errors.Is(err, ErrIdentityDeliveryLeaseLost) ||
		errors.Is(err, ErrIdentityDeliveryLeaseExpired) {
		t.Fatalf("expected lease lost mapping, got %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityDeliveryCompletePersistsAcceptanceAfterChallengeExpiry(t *testing.T) {
	t.Parallel()
	db, mock, store := newPostgresIdentityDeliveryMock(t)
	defer db.Close()
	base := time.Date(2026, 7, 11, 9, 0, 0, 0, time.UTC)
	task := validPostgresIdentityDeliveryTask(base)
	task.ChallengeExpiresAt = base.Add(2 * time.Minute)
	task.LeaseExpiresAt = base.Add(5 * time.Minute)
	completedAt := base.Add(3 * time.Minute)
	acceptance := IdentityDeliveryProviderAcceptance{
		Reference:  "provider-ref:relay-boundary",
		AcceptedAt: base.Add(time.Minute),
	}
	expectPostgresIdentityDeliveryScope(mock, task.TenantID, task.ProjectID)
	mock.ExpectQuery("a1_complete_identity_delivery_outbox").
		WithArgs(
			task.TenantID, task.ProjectID, task.ID, task.LeaseOwner,
			task.LeaseGeneration, acceptance.Reference, acceptance.AcceptedAt,
			completedAt,
		).
		WillReturnRows(sqlmock.NewRows([]string{"outbox_id"}).AddRow(task.ID))
	mock.ExpectCommit()
	if err := store.CompleteIdentityDelivery(
		context.Background(), task, acceptance, completedAt,
	); err != nil {
		t.Fatalf("complete accepted delivery after challenge expiry: %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityDeliveryCompleteRejectsAcceptanceAfterExpiryBeforeQuery(t *testing.T) {
	t.Parallel()
	db, mock, store := newPostgresIdentityDeliveryMock(t)
	defer db.Close()
	now := time.Date(2026, 7, 11, 9, 0, 0, 0, time.UTC)
	task := validPostgresIdentityDeliveryTask(now)
	acceptance := IdentityDeliveryProviderAcceptance{
		Reference:  "provider-ref:too-late",
		AcceptedAt: task.ChallengeExpiresAt,
	}
	if err := store.CompleteIdentityDelivery(
		context.Background(), task, acceptance, now,
	); err == nil {
		t.Fatal("provider acceptance at challenge expiry was accepted")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresIdentityDeliveryRetryAndDeadLetterUseFullFence(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 7, 11, 9, 0, 10, 0, time.UTC)
	task := validPostgresIdentityDeliveryTask(now)

	t.Run("retry", func(t *testing.T) {
		db, mock, store := newPostgresIdentityDeliveryMock(t)
		defer db.Close()
		availableAt := now.Add(7 * time.Second)
		expectPostgresIdentityDeliveryScope(mock, task.TenantID, task.ProjectID)
		mock.ExpectQuery("a1_retry_identity_delivery_outbox").
			WithArgs(
				task.TenantID, task.ProjectID, task.ID, task.LeaseOwner,
				task.LeaseGeneration, "smtp_delivery_failed", availableAt, now,
			).
			WillReturnRows(sqlmock.NewRows([]string{"outbox_id"}).AddRow(task.ID))
		mock.ExpectCommit()
		if err := store.RetryIdentityDelivery(
			context.Background(), task, "SMTP_DELIVERY_FAILED", availableAt, now,
		); err != nil {
			t.Fatalf("retry: %v", err)
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})

	t.Run("dead-letter", func(t *testing.T) {
		db, mock, store := newPostgresIdentityDeliveryMock(t)
		defer db.Close()
		expectPostgresIdentityDeliveryScope(mock, task.TenantID, task.ProjectID)
		mock.ExpectQuery("a1_dead_letter_identity_delivery_outbox").
			WithArgs(
				task.TenantID, task.ProjectID, task.ID, task.LeaseOwner,
				task.LeaseGeneration, "challenge_expired", now,
			).
			WillReturnRows(sqlmock.NewRows([]string{"outbox_id"}).AddRow(task.ID))
		mock.ExpectCommit()
		if err := store.DeadLetterIdentityDelivery(
			context.Background(), task, "challenge_expired", now,
		); err != nil {
			t.Fatalf("dead-letter: %v", err)
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})
}

func TestPostgresIdentityDeliveryRedriveReturnsAuditReceipt(t *testing.T) {
	t.Parallel()
	db, mock, store := newPostgresIdentityDeliveryMock(t)
	defer db.Close()

	now := time.Date(2026, 7, 11, 9, 5, 0, 0, time.UTC)
	command := IdentityDeliveryRedriveCommand{
		IdentityDeliveryRedriveRequest: IdentityDeliveryRedriveRequest{
			TaskID: postgresDeliveryTaskID, TenantID: postgresDeliveryOrganizationID,
			ProjectID: postgresDeliveryProjectID, ExpectedLeaseGeneration: 9,
			ActorID: "operator-1", ReasonCode: "provider_recovered", RequestID: "request-1",
		},
		RequestedAt: now,
	}
	expectPostgresIdentityDeliveryScope(mock, command.TenantID, command.ProjectID)
	mock.ExpectQuery("a1_redrive_identity_delivery_outbox").
		WithArgs(
			command.TenantID, command.ProjectID, command.TaskID,
			int64(9), command.ActorID, command.ReasonCode, command.RequestID, now,
		).
		WillReturnRows(sqlmock.NewRows([]string{
			"outbox_id", "lease_generation", "audit_id", "redriven_at",
		}).AddRow(command.TaskID, int64(10), postgresDeliveryAuditID, now))
	mock.ExpectCommit()

	receipt, err := store.RedriveIdentityDelivery(context.Background(), command)
	if err != nil {
		t.Fatalf("redrive: %v", err)
	}
	if receipt.TaskID != command.TaskID || receipt.LeaseGeneration != 10 ||
		receipt.AuditID != postgresDeliveryAuditID || !receipt.RedrivenAt.Equal(now) {
		t.Fatalf("invalid redrive receipt: %#v", receipt)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestMapPostgresIdentityDeliveryErrors(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name   string
		code   string
		target error
	}{
		{name: "lease expired", code: postgresIdentityDeliveryLeaseExpiredSQLState, target: ErrIdentityDeliveryLeaseExpired},
		{name: "challenge expired", code: postgresIdentityDeliveryChallengeExpiredState, target: ErrIdentityDeliveryLeaseExpired},
		{name: "lease lost", code: postgresIdentityDeliveryLeaseLostSQLState, target: ErrIdentityDeliveryLeaseLost},
		{name: "serialization fence", code: postgresIdentityDeliverySerializationSQLState, target: ErrIdentityDeliveryLeaseLost},
		{name: "scope", code: postgresIdentityDeliveryInsufficientPrivilege, target: ErrIdentityDeliveryScope},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			err := mapPostgresIdentityDeliveryError("test", &pq.Error{
				Code: pq.ErrorCode(test.code), Message: "public-safe failure",
			})
			if !errors.Is(err, test.target) {
				t.Fatalf("SQLSTATE %s mapped to %v", test.code, err)
			}
		})
	}
}

func TestPostgresIdentityDeliveryLiveContention(t *testing.T) {
	runtimeDSN := os.Getenv("ASHR_IDENTITY_DELIVERY_LIVE_DSN")
	adminDSN := os.Getenv("ASHR_IDENTITY_DELIVERY_LIVE_ADMIN_DSN")
	if runtimeDSN == "" || adminDSN == "" {
		t.Skip("set ASHR_IDENTITY_DELIVERY_LIVE_DSN and ASHR_IDENTITY_DELIVERY_LIVE_ADMIN_DSN for the disposable PostgreSQL harness")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	admin, err := sql.Open("postgres", adminDSN)
	if err != nil {
		t.Fatal("open live admin database")
	}
	defer admin.Close()
	if err := admin.PingContext(ctx); err != nil {
		t.Skip("live admin PostgreSQL is unavailable")
	}

	organizationID := livePostgresIdentityDeliveryUUID(t)
	workspaceID := livePostgresIdentityDeliveryUUID(t)
	projectID := livePostgresIdentityDeliveryUUID(t)
	challengeID := livePostgresIdentityDeliveryUUID(t)
	suffix := organizationID[:8]
	digest := func(label string) string {
		encoded := hex.EncodeToString([]byte(label + suffix))
		for len(encoded) < 64 {
			encoded += encoded
		}
		return encoded[:64]
	}
	_, err = admin.ExecContext(ctx, `
INSERT INTO organizations (id, slug, display_name)
VALUES ($1::uuid, $2, $3);
INSERT INTO workspaces (id, organization_id, slug, display_name)
VALUES ($4::uuid, $1::uuid, $5, $6);
INSERT INTO projects (id, organization_id, workspace_id, slug, display_name)
VALUES ($7::uuid, $1::uuid, $4::uuid, $8, $9);
INSERT INTO identity_verification_challenges (
  id, organization_id, project_id, channel, purpose, subject_digest,
  challenge_digest, code_digest, request_context_digest, expires_at
) VALUES (
  $10::uuid, $1::uuid, $7::uuid, 'email', 'login', $11, $12, $13, $14,
  clock_timestamp() + interval '10 minutes'
);
INSERT INTO identity_verification_delivery_outbox (
  organization_id, project_id, challenge_id, channel, purpose,
  subject_digest, delivery_digest
) VALUES ($1::uuid, $7::uuid, $10::uuid, 'email', 'login', $11, $15);
`, organizationID, "delivery-org-"+suffix, "Delivery live organization",
		workspaceID, "delivery-workspace-"+suffix, "Delivery live workspace",
		projectID, "delivery-project-"+suffix, "Delivery live project",
		challengeID, digest("subject"), digest("challenge"), digest("code"),
		digest("context"), digest("delivery"))
	if err != nil {
		t.Fatalf("prepare live identity delivery fixture: %v", err)
	}

	dbOne, err := sql.Open("postgres", runtimeDSN)
	if err != nil {
		t.Fatal("open first live runtime database")
	}
	defer dbOne.Close()
	dbTwo, err := sql.Open("postgres", runtimeDSN)
	if err != nil {
		t.Fatal("open second live runtime database")
	}
	defer dbTwo.Close()
	storeOne, _ := NewPostgresIdentityDeliveryOutboxStore(dbOne)
	storeTwo, _ := NewPostgresIdentityDeliveryOutboxStore(dbTwo)

	start := make(chan struct{})
	results := make(chan []IdentityDeliveryTask, 2)
	errorsSeen := make(chan error, 2)
	var wait sync.WaitGroup
	for index, store := range []*PostgresIdentityDeliveryOutboxStore{storeOne, storeTwo} {
		wait.Add(1)
		go func(index int, store *PostgresIdentityDeliveryOutboxStore) {
			defer wait.Done()
			<-start
			tasks, claimErr := store.ClaimIdentityDeliveries(
				ctx, organizationID, projectID, fmt.Sprintf("live-worker-%d", index+1),
				1, 30*time.Second, time.Now().UTC(),
			)
			results <- tasks
			errorsSeen <- claimErr
		}(index, store)
	}
	close(start)
	wait.Wait()
	close(results)
	close(errorsSeen)
	for claimErr := range errorsSeen {
		if claimErr != nil {
			t.Fatalf("live claim: %v", claimErr)
		}
	}
	claimed := 0
	for tasks := range results {
		claimed += len(tasks)
	}
	if claimed != 1 {
		t.Fatalf("two independent connections produced %d leases for one outbox row", claimed)
	}
}

func newPostgresIdentityDeliveryMock(
	t *testing.T,
) (*sql.DB, sqlmock.Sqlmock, *PostgresIdentityDeliveryOutboxStore) {
	t.Helper()
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	store, err := NewPostgresIdentityDeliveryOutboxStore(db)
	if err != nil {
		db.Close()
		t.Fatal(err)
	}
	return db, mock, store
}

func expectPostgresIdentityDeliveryScope(
	mock sqlmock.Sqlmock,
	tenantID string,
	projectID string,
) {
	mock.ExpectBegin()
	mock.ExpectExec("SELECT set_config").
		WithArgs(tenantID, projectID).
		WillReturnResult(sqlmock.NewResult(0, 1))
}

func validPostgresIdentityDeliveryTask(now time.Time) IdentityDeliveryTask {
	return IdentityDeliveryTask{
		ID: postgresDeliveryTaskID, TenantID: postgresDeliveryOrganizationID,
		ProjectID: postgresDeliveryProjectID, ChallengeID: postgresDeliveryChallengeID,
		Channel: IdentityVerificationEmail, Purpose: IdentityVerificationBinding,
		OpaqueRef: "vault:identity-delivery/task-1", ChallengeExpiresAt: now.Add(10 * time.Minute),
		Attempt: 2, MaxAttempts: 8,
		ProviderIdempotencyKey: "identity-delivery:44444444-4444-4444-8444-444444444444:0",
		LeaseOwner:             "worker-a", LeaseGeneration: 9,
		LeaseExpiresAt: now.Add(30 * time.Second),
	}
}

func livePostgresIdentityDeliveryUUID(t *testing.T) string {
	t.Helper()
	value := make([]byte, 16)
	if _, err := cryptorand.Read(value); err != nil {
		t.Fatal(err)
	}
	value[6] = (value[6] & 0x0f) | 0x40
	value[8] = (value[8] & 0x3f) | 0x80
	encoded := hex.EncodeToString(value)
	return encoded[0:8] + "-" + encoded[8:12] + "-" + encoded[12:16] + "-" +
		encoded[16:20] + "-" + encoded[20:32]
}
