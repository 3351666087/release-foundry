package releasefoundry

import (
	"context"
	"errors"
	"testing"
	"time"
)

type verificationTransactionTestIdentityStore struct {
	account        IdentityAccountDTO
	credential     IdentityCredentialDTO
	createFailures int
}

func (store *verificationTransactionTestIdentityStore) GetAccount(_ context.Context, accountID string) (IdentityAccountDTO, error) {
	if accountID != store.account.AccountID {
		return IdentityAccountDTO{}, ErrIdentityAccountNotFound
	}
	return store.account, nil
}

func (*verificationTransactionTestIdentityStore) HasLoginCredential(context.Context, string, IdentityCredentialInput) (bool, error) {
	return false, nil
}

func (store *verificationTransactionTestIdentityStore) CreateVerifiedAccount(
	context.Context,
	CreateIdentityAccountRequest,
) (IdentityAccountDTO, IdentityCredentialDTO, error) {
	if store.createFailures > 0 {
		store.createFailures--
		return IdentityAccountDTO{}, IdentityCredentialDTO{}, errors.New("identity transaction rolled back")
	}
	return store.account, store.credential, nil
}

func (store *verificationTransactionTestIdentityStore) LinkVerifiedCredential(
	context.Context,
	string,
	LinkIdentityCredentialRequest,
) (IdentityCredentialDTO, bool, error) {
	return store.credential, true, nil
}

func (store *verificationTransactionTestIdentityStore) AuthenticateVerifiedCredential(
	context.Context,
	string,
	IdentityCredentialInput,
) (IdentityAuthenticationDTO, error) {
	return IdentityAuthenticationDTO{Account: store.account, Credential: store.credential}, nil
}

type recordingVerificationTransactionCoordinator struct {
	delegate IdentityVerificationTransactionCoordinator
	calls    int
}

func (coordinator *recordingVerificationTransactionCoordinator) CompleteIdentityVerification(
	ctx context.Context,
	command IdentityVerificationCompletionCommand,
) (IdentityVerificationResultDTO, error) {
	coordinator.calls++
	return coordinator.delegate.CompleteIdentityVerification(ctx, command)
}

func TestIdentityVerificationTransactionDoesNotConsumeReceiptWhenMutationRollsBack(t *testing.T) {
	now := time.Date(2026, 7, 11, 9, 0, 0, 0, time.UTC)
	challenges := NewMemoryIdentityVerificationStore(func() time.Time { return now })
	sender := &MemoryIdentityVerificationSender{}
	identity := &verificationTransactionTestIdentityStore{
		account: IdentityAccountDTO{
			SchemaVersion: UnifiedIdentitySchemaVersion,
			AccountID:     "acct_transaction",
			PrimaryID:     "prn_transaction",
			Status:        "active",
			CreatedAt:     now,
			UpdatedAt:     now,
		},
		credential: IdentityCredentialDTO{
			SchemaVersion: UnifiedIdentitySchemaVersion,
			CredentialID:  "cred_transaction",
			Kind:          IdentityCredentialEmail,
			Provider:      IdentityProviderLocal,
			Verified:      true,
			CanLogin:      true,
			LinkedAt:      now,
		},
		createFailures: 1,
	}
	coordinator := &recordingVerificationTransactionCoordinator{
		delegate: localIdentityVerificationTransactionCoordinator{store: challenges, identity: identity},
	}
	service, err := NewIdentityVerificationService(IdentityVerificationServiceOptions{
		Store: challenges, Sender: sender, IdentityStore: identity,
		TransactionCoordinator: coordinator,
		Now:                    func() time.Time { return now },
		DigestKey:              []byte("verification-transaction-key-32-bytes"),
		TTL:                    5 * time.Minute,
		AttemptCap:             3,
		ResendCooldown:         time.Minute,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(service.Close)

	start, err := service.Start(context.Background(), IdentityVerificationStartRequest{
		Channel: IdentityVerificationEmail, Identifier: "transaction@example.test",
		Purpose: IdentityVerificationBinding, TenantID: "tenant-transaction",
	})
	if err != nil {
		t.Fatalf("start verification: %v", err)
	}
	code := lastVerificationCode(t, sender)
	request := IdentityVerificationCompleteRequest{
		ChallengeID: start.ChallengeID, Code: code,
		Channel: IdentityVerificationEmail, Identifier: "transaction@example.test",
		Purpose: IdentityVerificationBinding, TenantID: "tenant-transaction",
	}
	if _, err := service.Complete(context.Background(), request); err == nil {
		t.Fatal("expected the first identity mutation to roll back")
	}
	result, err := service.Complete(context.Background(), request)
	if err != nil {
		t.Fatalf("receipt was consumed before the identity mutation committed: %v", err)
	}
	if result.Account.AccountID != identity.account.AccountID ||
		result.Credential.CredentialID != identity.credential.CredentialID ||
		!result.Created {
		t.Fatalf("unexpected committed result: %#v", result)
	}
	if coordinator.calls != 2 {
		t.Fatalf("transaction coordinator calls=%d, want 2", coordinator.calls)
	}
	if _, err := service.Complete(context.Background(), request); !errors.Is(err, ErrIdentityVerificationConsumed) {
		t.Fatalf("committed receipt remained reusable: %v", err)
	}
}

var _ IdentityVerificationIdentityStore = (*verificationTransactionTestIdentityStore)(nil)
