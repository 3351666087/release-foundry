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
			return result, err
		}
		timer := time.NewTimer(time.Duration(attempt+1) * 5 * time.Millisecond)
		select {
		case <-ctx.Done():
			timer.Stop()
			return IdentityCredentialLinkResultDTO{}, ctx.Err()
		case <-timer.C:
		}
	}
	return IdentityCredentialLinkResultDTO{}, fmt.Errorf("identity credential-link transaction remained contended")
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
	subjectDigest := coordinator.receipts.receiptDigest(
		"credential-link:consumed-replay:" + locked.metadata.Digest,
	)
	emailDigest := ""
	credentialKind := postgresIdentityCredentialKind(
		IdentityCredentialOAuth, command.Provider,
	)
	if !consumed {
		proof := locked.proof
		subjectDigest = coordinator.receipts.receiptDigest(
			"credential:" + string(proof.Provider) + ":" + proof.Identifier,
		)
		if strings.TrimSpace(proof.VerifiedEmail) != "" {
			emailDigest = coordinator.receipts.receiptDigest(
				"email:" + strings.ToLower(strings.TrimSpace(proof.VerifiedEmail)),
			)
		}
		credentialKind = postgresIdentityCredentialKind(proof.Kind, proof.Provider)
	}
	idempotencyDigest := coordinator.receipts.receiptDigest(
		"credential-link:idempotency:" + command.AccountID + ":" + command.IdempotencyKey,
	)
	requestDigest := coordinator.receipts.receiptDigest(strings.Join([]string{
		"credential-link:request", command.AccountID, command.ActorID,
		command.SessionID, command.TenantID, command.ProjectID,
		string(command.Provider), locked.metadata.Digest,
	}, "\x00"))
	eventDigest := coordinator.receipts.receiptDigest(
		"credential-link:event:" + requestDigest,
	)
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
		if isPostgresUniqueViolation(err) {
			return IdentityCredentialLinkResultDTO{}, IdentityDomainError{
				Code:    "identity_credential_link_conflict",
				Message: "credential or canonical email is already linked",
			}
		}
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
	locked := lockedIdentityLifecycleReceipt{metadata: metadata}
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

var _ IdentityCredentialLinkCoordinator = (*PostgresIdentityCredentialLinkCoordinator)(nil)
