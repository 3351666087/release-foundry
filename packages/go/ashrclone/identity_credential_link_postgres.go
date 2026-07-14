package ashrclone

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/lib/pq"
)

// PostgresIdentityCredentialLinkCoordinator is the production, single
// transaction boundary for explicit existing-account credential linking.
type PostgresIdentityCredentialLinkCoordinator struct {
	store    *ProductionIdentityStore
	receipts *postgresIdentityLifecycleReceiptStore
}

func NewPostgresIdentityCredentialLinkCoordinator(
	store *ProductionIdentityStore,
	receipts IdentityLifecycleReceiptStore,
) (*PostgresIdentityCredentialLinkCoordinator, error) {
	receiptStore, ok := receipts.(*postgresIdentityLifecycleReceiptStore)
	if store == nil || store.db == nil || store.lifecycleKeys == nil ||
		!ok || receiptStore.db != store.db {
		return nil, fmt.Errorf("postgres credential-link coordinator requires one production identity and receipt database")
	}
	return &PostgresIdentityCredentialLinkCoordinator{store: store, receipts: receiptStore}, nil
}

func (coordinator *PostgresIdentityCredentialLinkCoordinator) CompleteIdentityCredentialLink(
	ctx context.Context,
	command IdentityCredentialLinkCommand,
	now time.Time,
) (IdentityCredentialLinkResultDTO, error) {
	const maxAttempts = 8
	for attempt := 0; attempt < maxAttempts; attempt++ {
		result, err := coordinator.completeOnce(ctx, command, now.UTC())
		if !isPostgresTransactionRetryable(err) {
			return result, mapPostgresIdentityCredentialLinkError(err)
		}
		timer := time.NewTimer(time.Duration(attempt+1) * 5 * time.Millisecond)
		select {
		case <-ctx.Done():
			timer.Stop()
			return IdentityCredentialLinkResultDTO{}, ctx.Err()
		case <-timer.C:
		}
	}
	return IdentityCredentialLinkResultDTO{}, identityCredentialLinkError(
		"identity_credential_link_unavailable",
		"credential linking is temporarily unavailable",
	)
}

func (coordinator *PostgresIdentityCredentialLinkCoordinator) completeOnce(
	ctx context.Context,
	command IdentityCredentialLinkCommand,
	now time.Time,
) (IdentityCredentialLinkResultDTO, error) {
	operationCtx, cancel := context.WithTimeout(ctx, coordinator.store.sqlTimeout)
	defer cancel()
	tx, err := coordinator.store.db.BeginTx(operationCtx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return IdentityCredentialLinkResultDTO{}, err
	}
	defer tx.Rollback()
	if err := configureIdentityLifecycleTx(
		operationCtx, tx, coordinator.store.statementTimeout, coordinator.store.lockTimeout,
	); err != nil {
		return IdentityCredentialLinkResultDTO{}, err
	}
	if _, err := tx.ExecContext(operationCtx, `
SELECT set_config('app.a1_organization_id',$1,true),
       set_config('app.a1_project_id',$2,true),
       set_config('app.a1_principal_id',$3,true)
`, command.TenantID, command.ProjectID, command.AccountID); err != nil {
		return IdentityCredentialLinkResultDTO{}, err
	}

	request := CompleteIdentityLifecycleRequest{
		ReceiptID: command.ProofReceiptID, Provider: command.Provider,
		TenantID: command.TenantID, ProjectID: command.ProjectID,
	}
	locked, consumed, err := coordinator.lockCredentialLinkReceipt(
		operationCtx, tx, request, now,
	)
	if err != nil {
		return IdentityCredentialLinkResultDTO{}, err
	}
	digest := func(value string) (string, error) {
		return coordinator.receipts.keys.receiptDigestForVersion(
			value, locked.lookupKeyVersion,
		)
	}
	subjectDigest, err := digest(
		"credential-link:consumed-replay:" + locked.metadata.Digest,
	)
	if err != nil {
		return IdentityCredentialLinkResultDTO{}, err
	}
	emailDigest := ""
	credentialKind := postgresIdentityCredentialKind(
		IdentityCredentialOAuth, command.Provider,
	)
	if !consumed {
		proof := locked.proof
		subjectDigest, err = digest(
			"credential:" + string(proof.Provider) + ":" + proof.Identifier,
		)
		if err != nil {
			return IdentityCredentialLinkResultDTO{}, err
		}
		if strings.TrimSpace(proof.VerifiedEmail) != "" {
			emailDigest, err = digest(
				"email:" + strings.ToLower(strings.TrimSpace(proof.VerifiedEmail)),
			)
			if err != nil {
				return IdentityCredentialLinkResultDTO{}, err
			}
		}
		credentialKind = postgresIdentityCredentialKind(proof.Kind, proof.Provider)
	}
	idempotencyDigest, err := digest(
		"credential-link:idempotency:" + command.AccountID + ":" + command.IdempotencyKey,
	)
	if err != nil {
		return IdentityCredentialLinkResultDTO{}, err
	}
	requestDigest, err := digest(strings.Join([]string{
		"credential-link:request", command.AccountID, command.ActorID,
		command.SessionID, command.TenantID, command.ProjectID,
		string(command.Provider), locked.metadata.Digest,
	}, "\x00"))
	if err != nil {
		return IdentityCredentialLinkResultDTO{}, err
	}
	eventDigest, err := digest(
		"credential-link:event:" + requestDigest,
	)
	if err != nil {
		return IdentityCredentialLinkResultDTO{}, err
	}
	metadata, _ := json.Marshal(map[string]any{
		"source":         "identity_credential_link",
		"provider":       postgresIdentityProvider(command.Provider),
		"schema_version": IdentityCredentialLinkSchemaVersion,
	})
	var credentialID string
	var credentialAdded bool
	var linkedAt time.Time
	err = tx.QueryRowContext(operationCtx, `
SELECT linked_credential_id::text,credential_added,linked_at
FROM a1_complete_identity_credential_link(
  $1::uuid,$2::uuid,$3,$4::uuid,$5,$6,$7,NULLIF($8,''),
  $9,$10,$11,$12,$13,$14,$15::jsonb
)
`, command.TenantID, command.ProjectID, locked.metadata.Digest,
		command.AccountID, postgresIdentityProvider(command.Provider),
		credentialKind,
		subjectDigest, emailDigest, command.SessionDigest,
		command.MutationTicketID, command.StepUpReceiptID,
		idempotencyDigest, requestDigest, eventDigest, metadata).
		Scan(&credentialID, &credentialAdded, &linkedAt)
	if err != nil {
		return IdentityCredentialLinkResultDTO{}, err
	}
	account, err := (&PostgresIdentityLifecycleTransactionCoordinator{
		store: coordinator.store, receipts: coordinator.receipts,
	}).projectAccount(operationCtx, tx, command.AccountID)
	if err != nil {
		return IdentityCredentialLinkResultDTO{}, err
	}
	var credential IdentityCredentialDTO
	for _, item := range account.Credentials {
		if item.CredentialID == credentialID {
			credential = item
			break
		}
	}
	if credential.CredentialID == "" {
		return IdentityCredentialLinkResultDTO{}, errors.New("linked identity credential projection is unavailable")
	}
	if err := tx.Commit(); err != nil {
		return IdentityCredentialLinkResultDTO{}, err
	}
	return IdentityCredentialLinkResultDTO{
		SchemaVersion: IdentityCredentialLinkSchemaVersion,
		AccountID:     command.AccountID, Credential: credential,
		CredentialAdded: credentialAdded, SecurityPosture: account.SecurityPosture,
		LinkedAt: linkedAt.UTC(),
	}, nil
}

func (coordinator *PostgresIdentityCredentialLinkCoordinator) lockCredentialLinkReceipt(
	ctx context.Context,
	tx *sql.Tx,
	request CompleteIdentityLifecycleRequest,
	now time.Time,
) (lockedIdentityLifecycleReceipt, bool, error) {
	digests := coordinator.receipts.keys.receiptDigests(request.ReceiptID)
	var metadata identityLifecycleReceiptMetadata
	var nonce, ciphertext []byte
	var consumedAt sql.NullTime
	metadata.SchemaVersion = IdentityLifecycleSchemaVersion
	err := tx.QueryRowContext(ctx, `
SELECT receipt_digest,operation,provider,tenant_scope,project_scope,expires_at,
       consumed_at,proof_nonce,proof_key_version,proof_ciphertext
FROM a1_lock_identity_credential_link_receipt($1)
`, pq.Array(digests)).Scan(
		&metadata.Digest, &metadata.Operation, &metadata.Provider,
		&metadata.TenantScope, &metadata.ProjectScope, &metadata.ExpiresAt,
		&consumedAt, &nonce, &metadata.KeyVersion, &ciphertext,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return lockedIdentityLifecycleReceipt{}, false, ErrIdentityProofReceiptNotFound
	}
	if err != nil {
		return lockedIdentityLifecycleReceipt{}, false, err
	}
	if metadata.Operation != IdentityOperationCredentialLink ||
		metadata.Provider != normalizeIdentityLifecycleProvider(request.Provider) ||
		metadata.TenantScope != strings.TrimSpace(request.TenantID) ||
		metadata.ProjectScope != strings.TrimSpace(request.ProjectID) {
		return lockedIdentityLifecycleReceipt{}, false, ErrIdentityProofScopeMismatch
	}
	lookupKeyVersion, err := coordinator.receipts.keys.lookupVersionForDigest(
		request.ReceiptID, metadata.Digest,
	)
	if err != nil {
		return lockedIdentityLifecycleReceipt{}, false, err
	}
	locked := lockedIdentityLifecycleReceipt{
		metadata: metadata, lookupKeyVersion: lookupKeyVersion,
	}
	if consumedAt.Valid {
		// Exact replay is authorized by PostgreSQL using the persisted keyed
		// request fingerprints. Do not decrypt a completed proof: its old
		// encryption key may already have been retired.
		return locked, true, nil
	}
	if !now.UTC().Before(metadata.ExpiresAt.UTC()) {
		return lockedIdentityLifecycleReceipt{}, false, ErrIdentityProofReceiptExpired
	}
	proof, err := coordinator.receipts.keys.open(metadata, nonce, ciphertext)
	if err != nil {
		return lockedIdentityLifecycleReceipt{}, false, err
	}
	locked.proof = proof
	return locked, false, nil
}

func mapPostgresIdentityCredentialLinkError(err error) error {
	if err == nil {
		return nil
	}
	if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
		return err
	}
	for _, target := range []error{
		ErrIdentityProofReceiptNotFound,
		ErrIdentityProofReceiptConsumed,
		ErrIdentityProofReceiptExpired,
		ErrIdentityProofScopeMismatch,
	} {
		if errors.Is(err, target) {
			return target
		}
	}
	var domain IdentityDomainError
	if errors.As(err, &domain) {
		return domain
	}
	var postgresError *pq.Error
	if errors.As(err, &postgresError) {
		switch {
		case postgresError.Code == "23505":
			return identityCredentialLinkError(
				"identity_credential_link_conflict",
				"credential or canonical email is already linked",
			)
		case postgresError.Code == "22023",
			postgresError.Code == "42501",
			postgresError.Code == "55000":
			return identityCredentialLinkError(
				"identity_credential_link_rejected",
				"credential linking authorization or state was rejected",
			)
		case postgresError.Code.Class() == "08",
			postgresError.Code.Class() == "40",
			postgresError.Code.Class() == "53",
			postgresError.Code.Class() == "54",
			postgresError.Code.Class() == "55",
			postgresError.Code.Class() == "57",
			postgresError.Code.Class() == "58":
			return identityCredentialLinkError(
				"identity_credential_link_unavailable",
				"credential linking is temporarily unavailable",
			)
		default:
			return identityCredentialLinkError(
				"identity_credential_link_rejected",
				"credential linking authorization or state was rejected",
			)
		}
	}
	return identityCredentialLinkError(
		"identity_credential_link_unavailable",
		"credential linking is temporarily unavailable",
	)
}

var _ IdentityCredentialLinkCoordinator = (*PostgresIdentityCredentialLinkCoordinator)(nil)
