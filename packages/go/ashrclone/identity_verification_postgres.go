package ashrclone

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"regexp"
	"strings"
	"time"
)

const (
	defaultPostgresIdentityVerificationTimeout = 5 * time.Second
	maxPostgresIdentityVerificationTimeout     = 30 * time.Second
	minPostgresIdentityVerificationDigestKey   = 32
	maxPostgresIdentityVerificationTTL         = 15 * time.Minute
)

var postgresIdentityVerificationUUIDPattern = regexp.MustCompile(
	`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`,
)

// PostgresIdentityVerificationStore is scoped to one organization/project.
// It uses only the SECURITY DEFINER functions installed by migrations
// 012-025;
// the runtime role does not need and must not receive direct table access.
type PostgresIdentityVerificationStore struct {
	db               *sql.DB
	organizationID   string
	projectID        string
	principalID      string
	digestKey        []byte
	operationTimeout time.Duration
	random           io.Reader
	sessionTokens    *identitySessionTokenCodec
}

type PostgresIdentityVerificationStoreOptions struct {
	DB               *sql.DB
	OrganizationID   string
	ProjectID        string
	PrincipalID      string
	DigestKey        []byte
	OperationTimeout time.Duration
	Random           io.Reader
	sessionTokens    *identitySessionTokenCodec
}

// PostgresIdentityVerificationProof contains the digest-only input required by
// migration 012. CandidateCodeDigest must be derived before this boundary; a
// raw OTP must never be passed to or persisted by this store.
type PostgresIdentityVerificationProof struct {
	ChallengeID          string
	CandidateCodeDigest  string
	RequestContextDigest string
	Metadata             map[string]any
}

type PostgresIdentityVerificationReceipt struct {
	OutcomeCode       string
	ChallengeID       string
	ReceiptID         string
	PrincipalID       string
	Channel           IdentityVerificationChannel
	Purpose           IdentityVerificationPurpose
	AttemptsRemaining int
}

// PostgresIdentityVerificationTransactionCoordinator verifies a digest proof
// and applies its identity mutation through migration 012's narrow SECURITY
// DEFINER functions in one sql.Tx.
type PostgresIdentityVerificationTransactionCoordinator struct {
	store *PostgresIdentityVerificationStore
}

func NewPostgresIdentityVerificationTransactionCoordinator(
	store *PostgresIdentityVerificationStore,
) (*PostgresIdentityVerificationTransactionCoordinator, error) {
	if store == nil || store.db == nil {
		return nil, fmt.Errorf("PostgreSQL identity verification store is required")
	}
	return &PostgresIdentityVerificationTransactionCoordinator{store: store}, nil
}

// NewPostgresIdentityVerificationStore is retained to make accidental use of
// the old unscoped constructor fail closed. Production callers must provide
// immutable UUID scope and digest material through the options constructor.
func NewPostgresIdentityVerificationStore(db *sql.DB) (*PostgresIdentityVerificationStore, error) {
	if db == nil {
		return nil, fmt.Errorf("PostgreSQL identity verification db is required")
	}
	return nil, fmt.Errorf(
		"PostgreSQL identity verification organization_id, project_id, and digest key are required",
	)
}

func NewPostgresIdentityVerificationStoreWithOptions(
	options PostgresIdentityVerificationStoreOptions,
) (*PostgresIdentityVerificationStore, error) {
	if options.DB == nil {
		return nil, fmt.Errorf("PostgreSQL identity verification db is required")
	}
	options.OrganizationID = strings.TrimSpace(options.OrganizationID)
	options.ProjectID = strings.TrimSpace(options.ProjectID)
	options.PrincipalID = strings.TrimSpace(options.PrincipalID)
	if !validPostgresIdentityVerificationUUID(options.OrganizationID) {
		return nil, fmt.Errorf("PostgreSQL identity verification organization_id must be a canonical UUID")
	}
	if !validPostgresIdentityVerificationUUID(options.ProjectID) {
		return nil, fmt.Errorf("PostgreSQL identity verification project_id must be a canonical UUID")
	}
	if options.PrincipalID != "" && !validPostgresIdentityVerificationUUID(options.PrincipalID) {
		return nil, fmt.Errorf("PostgreSQL identity verification principal_id must be a canonical UUID")
	}
	if len(options.DigestKey) < minPostgresIdentityVerificationDigestKey {
		return nil, fmt.Errorf(
			"PostgreSQL identity verification digest key must contain at least %d bytes",
			minPostgresIdentityVerificationDigestKey,
		)
	}
	if options.OperationTimeout == 0 {
		options.OperationTimeout = defaultPostgresIdentityVerificationTimeout
	}
	if options.OperationTimeout < time.Millisecond ||
		options.OperationTimeout > maxPostgresIdentityVerificationTimeout {
		return nil, fmt.Errorf(
			"PostgreSQL identity verification operation timeout must be between 1ms and %s",
			maxPostgresIdentityVerificationTimeout,
		)
	}
	if options.Random == nil {
		options.Random = rand.Reader
	}
	return &PostgresIdentityVerificationStore{
		db:               options.DB,
		organizationID:   options.OrganizationID,
		projectID:        options.ProjectID,
		principalID:      options.PrincipalID,
		digestKey:        append([]byte(nil), options.DigestKey...),
		operationTimeout: options.OperationTimeout,
		random:           options.Random,
		sessionTokens:    options.sessionTokens,
	}, nil
}

func (store *PostgresIdentityVerificationStore) CreateIdentityVerificationChallenge(
	context.Context,
	IdentityVerificationChallenge,
	time.Duration,
) error {
	if store == nil || store.db == nil {
		return identityVerificationStoreUnavailable()
	}
	return IdentityVerificationError{
		Code:    "verification_delivery_seal_required",
		Message: "identity verification delivery requires a sealed payload",
	}
}

func (store *PostgresIdentityVerificationStore) IdentityVerificationDeliveryScope() (string, string) {
	if store == nil {
		return "", ""
	}
	return store.organizationID, store.projectID
}

func (store *PostgresIdentityVerificationStore) CreateIdentityVerificationChallengeWithDelivery(
	ctx context.Context,
	challenge IdentityVerificationChallenge,
	resendCooldown time.Duration,
	deliveryReservationID string,
	opaqueRef string,
) error {
	if store == nil || store.db == nil {
		return identityVerificationStoreUnavailable()
	}
	if err := store.validateChallenge(challenge, resendCooldown); err != nil {
		return err
	}
	if !validPostgresIdentityVerificationUUID(deliveryReservationID) ||
		!identityDeliveryOpaqueReferencePattern.MatchString(opaqueRef) {
		return invalidPostgresIdentityVerificationChallenge()
	}
	metadata, err := json.Marshal(map[string]any{
		"source": "go_identity_verification_delivery_store",
	})
	if err != nil {
		return identityVerificationStoreUnavailable()
	}
	requestContextDigest := store.requestContextDigest(challenge)
	eventDigest, err := store.uniqueDigest("issue-event", challenge.ChallengeID)
	if err != nil {
		return identityVerificationStoreUnavailable()
	}

	operationCtx, cancel := store.boundedContext(ctx)
	defer cancel()
	tx, err := store.db.BeginTx(operationCtx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return identityVerificationStoreUnavailable()
	}
	defer func() { _ = tx.Rollback() }()
	if err := setPostgresIdentityVerificationScope(
		operationCtx, tx, store.organizationID, store.projectID,
	); err != nil {
		return identityVerificationStoreUnavailable()
	}

	var databaseChallengeID sql.NullString
	var accepted bool
	var retryAfterSeconds int
	err = tx.QueryRowContext(operationCtx, `
SELECT challenge_id::text, accepted, retry_after_seconds
  FROM a1_issue_identity_verification_challenge_with_delivery(
    p_organization_id => $1::uuid,
    p_project_id => $2::uuid,
    p_principal_id => NULLIF($3, '')::uuid,
    p_channel => $4,
    p_purpose => $5,
    p_subject_digest => $6,
    p_challenge_digest => $7,
    p_code_digest => $8,
    p_request_context_digest => $9,
    p_expires_at => $10,
    p_max_attempts => $11,
    p_cooldown_seconds => $12,
    p_event_digest => $13,
    p_opaque_ref => $14,
    p_metadata => $15::jsonb
  )
`,
		store.organizationID,
		store.projectID,
		store.challengePrincipalID(challenge),
		string(challenge.Channel),
		postgresIdentityVerificationPurpose(challenge.Purpose),
		challenge.IdentifierDigest,
		store.challengeDigest(challenge.ChallengeID),
		challenge.CodeDigest,
		requestContextDigest,
		challenge.ExpiresAt.UTC(),
		challenge.AttemptCap,
		int(resendCooldown/time.Second),
		eventDigest,
		opaqueRef,
		string(metadata),
	).Scan(&databaseChallengeID, &accepted, &retryAfterSeconds)
	if err != nil {
		return identityVerificationStoreUnavailable()
	}
	if !accepted {
		if err := tx.Commit(); err != nil {
			return identityVerificationStoreUnavailable()
		}
		return IdentityVerificationError{
			Code:    "verification_resend_cooldown",
			Message: "verification resend cooldown is active",
		}
	}
	if !databaseChallengeID.Valid || !validPostgresIdentityVerificationUUID(databaseChallengeID.String) {
		return identityVerificationStoreUnavailable()
	}
	if err := tx.Commit(); err != nil {
		return ErrIdentityVerificationDeliveryCommitUnknown
	}
	return nil
}

// VerifyConsumeIdentityVerificationChallenge performs the migration-native
// attempt/verify/consume operation atomically. A rejected result is deliberately
// non-enumerating; migration 012 does not expose whether the handle was absent,
// expired, already consumed, context-mismatched, or proof-mismatched.
func (store *PostgresIdentityVerificationStore) VerifyConsumeIdentityVerificationChallenge(
	ctx context.Context,
	proof PostgresIdentityVerificationProof,
) (PostgresIdentityVerificationReceipt, error) {
	if store == nil || store.db == nil {
		return PostgresIdentityVerificationReceipt{}, identityVerificationStoreUnavailable()
	}
	proof.ChallengeID = strings.TrimSpace(proof.ChallengeID)
	if !validPostgresIdentityVerificationHandle(proof.ChallengeID, "ivc_", 256) ||
		!validPostgresIdentityVerificationDigest(proof.CandidateCodeDigest) ||
		!validPostgresIdentityVerificationDigest(proof.RequestContextDigest) {
		return PostgresIdentityVerificationReceipt{}, invalidPostgresIdentityVerificationProof()
	}
	metadata, err := marshalPostgresIdentityVerificationMetadata(proof.Metadata)
	if err != nil {
		return PostgresIdentityVerificationReceipt{}, invalidPostgresIdentityVerificationProof()
	}
	receiptDigest, err := store.uniqueDigest("receipt", proof.ChallengeID)
	if err != nil {
		return PostgresIdentityVerificationReceipt{}, identityVerificationStoreUnavailable()
	}
	eventDigest, err := store.uniqueDigest("verify-event", proof.ChallengeID)
	if err != nil {
		return PostgresIdentityVerificationReceipt{}, identityVerificationStoreUnavailable()
	}

	operationCtx, cancel := store.boundedContext(ctx)
	defer cancel()
	tx, err := store.db.BeginTx(operationCtx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return PostgresIdentityVerificationReceipt{}, identityVerificationStoreUnavailable()
	}
	defer func() { _ = tx.Rollback() }()
	if err := setPostgresIdentityVerificationScope(
		operationCtx, tx, store.organizationID, store.projectID,
	); err != nil {
		return PostgresIdentityVerificationReceipt{}, identityVerificationStoreUnavailable()
	}

	var receipt PostgresIdentityVerificationReceipt
	var databaseChallengeID, databaseReceiptID, principalID sql.NullString
	var channel, purpose sql.NullString
	err = tx.QueryRowContext(operationCtx, `
SELECT outcome_code,
       challenge_id::text,
       receipt_id::text,
       principal_id::text,
       channel,
       purpose,
       attempts_remaining
  FROM a1_verify_consume_identity_challenge(
    $1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8::jsonb
  )
`,
		store.organizationID,
		store.projectID,
		store.challengeDigest(proof.ChallengeID),
		proof.CandidateCodeDigest,
		proof.RequestContextDigest,
		receiptDigest,
		eventDigest,
		string(metadata),
	).Scan(
		&receipt.OutcomeCode,
		&databaseChallengeID,
		&databaseReceiptID,
		&principalID,
		&channel,
		&purpose,
		&receipt.AttemptsRemaining,
	)
	if err != nil {
		return PostgresIdentityVerificationReceipt{}, identityVerificationStoreUnavailable()
	}
	if err := tx.Commit(); err != nil {
		return PostgresIdentityVerificationReceipt{}, identityVerificationStoreUnavailable()
	}
	if receipt.OutcomeCode != "consumed" {
		return PostgresIdentityVerificationReceipt{}, IdentityVerificationError{
			Code:    "verification_rejected",
			Message: "verification proof was rejected",
		}
	}
	if !databaseChallengeID.Valid || !databaseReceiptID.Valid ||
		!validPostgresIdentityVerificationUUID(databaseChallengeID.String) ||
		!validPostgresIdentityVerificationUUID(databaseReceiptID.String) ||
		!channel.Valid || !purpose.Valid {
		return PostgresIdentityVerificationReceipt{}, identityVerificationStoreUnavailable()
	}
	receipt.ChallengeID = proof.ChallengeID
	receipt.ReceiptID = databaseReceiptID.String
	receipt.Channel = IdentityVerificationChannel(channel.String)
	receipt.Purpose, err = identityVerificationPurposeFromPostgres(purpose.String)
	if err != nil {
		return PostgresIdentityVerificationReceipt{}, identityVerificationStoreUnavailable()
	}
	if principalID.Valid {
		if !validPostgresIdentityVerificationUUID(principalID.String) {
			return PostgresIdentityVerificationReceipt{}, identityVerificationStoreUnavailable()
		}
		receipt.PrincipalID = principalID.String
	}
	return receipt, nil
}

// ConsumeIdentityVerificationChallenge cannot safely implement migration 012:
// its callback receives a stored code digest, while the SECURITY DEFINER
// function requires the caller's candidate digest and performs comparison
// inside PostgreSQL. Fail closed instead of restoring forbidden table reads.
func (store *PostgresIdentityVerificationStore) ConsumeIdentityVerificationChallenge(
	context.Context,
	string,
	func(IdentityVerificationChallenge) error,
) (IdentityVerificationChallenge, error) {
	return IdentityVerificationChallenge{}, IdentityVerificationError{
		Code:    "verification_durable_proof_required",
		Message: "durable identity verification requires a digest proof",
	}
}

func (*PostgresIdentityVerificationStore) IsProductionIdentityVerificationStore() {}

func (*PostgresIdentityVerificationStore) UsesTransactionalIdentityVerificationOutbox() {}

func (*PostgresIdentityVerificationTransactionCoordinator) IsProductionIdentityVerificationTransactionCoordinator() {
}

func (coordinator *PostgresIdentityVerificationTransactionCoordinator) CompleteIdentityVerification(
	ctx context.Context,
	command IdentityVerificationCompletionCommand,
) (IdentityVerificationResultDTO, error) {
	if command.Purpose == IdentityVerificationRegistration ||
		command.Purpose == IdentityVerificationLogin ||
		command.Purpose == IdentityVerificationRecovery {
		return IdentityVerificationResultDTO{}, IdentityVerificationError{
			Code:    "session_issuance_required",
			Message: "trusted identity session issuance is required",
		}
	}
	result, _, err := coordinator.completeIdentityVerification(ctx, command, false)
	return result, err
}

func (coordinator *PostgresIdentityVerificationTransactionCoordinator) CompleteIdentityVerificationAndIssueSession(
	ctx context.Context,
	command IdentityVerificationCompletionCommand,
) (IdentityVerificationResultDTO, IdentitySessionIssuanceReceipt, error) {
	if command.Purpose != IdentityVerificationRegistration &&
		command.Purpose != IdentityVerificationLogin &&
		command.Purpose != IdentityVerificationRecovery {
		return IdentityVerificationResultDTO{}, IdentitySessionIssuanceReceipt{}, IdentityVerificationError{
			Code:    "session_issuance_not_applicable",
			Message: "session issuance requires registration, login, or recovery verification",
		}
	}
	return coordinator.completeIdentityVerification(ctx, command, true)
}

func (coordinator *PostgresIdentityVerificationTransactionCoordinator) completeIdentityVerification(
	ctx context.Context,
	command IdentityVerificationCompletionCommand,
	issueSession bool,
) (IdentityVerificationResultDTO, IdentitySessionIssuanceReceipt, error) {
	if coordinator == nil || coordinator.store == nil || coordinator.store.db == nil {
		return IdentityVerificationResultDTO{}, IdentitySessionIssuanceReceipt{}, identityVerificationStoreUnavailable()
	}
	store := coordinator.store
	if err := validatePostgresIdentityVerificationCompletion(command, store); err != nil {
		return IdentityVerificationResultDTO{}, IdentitySessionIssuanceReceipt{}, err
	}
	var sessionToken identitySessionTokenMaterial
	var refreshToken identitySessionTokenMaterial
	if issueSession {
		if store.sessionTokens == nil {
			return IdentityVerificationResultDTO{}, IdentitySessionIssuanceReceipt{}, IdentityVerificationError{
				Code:    "session_issuance_unavailable",
				Message: "identity session issuance is unavailable",
			}
		}
	}
	requestContextDigest := store.requestContextDigest(IdentityVerificationChallenge{
		ChallengeID: command.ChallengeID, Channel: command.Channel,
		IdentifierDigest: command.IdentifierDigest, Purpose: command.Purpose,
		TenantID: command.TenantID, AccountID: command.AccountID,
	})
	receiptDigest, err := store.uniqueDigest("receipt", command.ChallengeID)
	if err != nil {
		return IdentityVerificationResultDTO{}, IdentitySessionIssuanceReceipt{}, identityVerificationStoreUnavailable()
	}
	verifyEventDigest, err := store.uniqueDigest("verify-event", command.ChallengeID)
	if err != nil {
		return IdentityVerificationResultDTO{}, IdentitySessionIssuanceReceipt{}, identityVerificationStoreUnavailable()
	}
	mutationEventDigest, err := store.uniqueDigest("mutation-event", command.ChallengeID)
	if err != nil {
		return IdentityVerificationResultDTO{}, IdentitySessionIssuanceReceipt{}, identityVerificationStoreUnavailable()
	}
	metadata, err := marshalPostgresIdentityVerificationMetadata(map[string]any{
		"source": "go_identity_verification_transaction_coordinator",
	})
	if err != nil {
		return IdentityVerificationResultDTO{}, IdentitySessionIssuanceReceipt{}, invalidPostgresIdentityVerificationProof()
	}

	operationCtx, cancel := store.boundedContext(ctx)
	defer cancel()
	tx, err := store.db.BeginTx(operationCtx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return IdentityVerificationResultDTO{}, IdentitySessionIssuanceReceipt{}, identityVerificationStoreUnavailable()
	}
	defer func() { _ = tx.Rollback() }()
	if err := setPostgresIdentityVerificationScope(
		operationCtx, tx, store.organizationID, store.projectID,
	); err != nil {
		return IdentityVerificationResultDTO{}, IdentitySessionIssuanceReceipt{}, identityVerificationStoreUnavailable()
	}

	receipt, err := store.verifyIdentityVerificationAttemptTx(
		operationCtx,
		tx,
		PostgresIdentityVerificationProof{
			ChallengeID:          command.ChallengeID,
			CandidateCodeDigest:  command.CandidateCodeDigest,
			RequestContextDigest: requestContextDigest,
			Metadata: map[string]any{
				"source": "go_identity_verification_transaction_coordinator",
			},
		},
		receiptDigest,
		verifyEventDigest,
	)
	if err != nil {
		if verificationErrorCode(err) == "verification_rejected" {
			if commitErr := tx.Commit(); commitErr != nil {
				return IdentityVerificationResultDTO{}, IdentitySessionIssuanceReceipt{}, identityVerificationStoreUnavailable()
			}
		}
		return IdentityVerificationResultDTO{}, IdentitySessionIssuanceReceipt{}, err
	}
	if issueSession {
		sessionToken, err = store.sessionTokens.issue()
		if err != nil {
			return IdentityVerificationResultDTO{}, IdentitySessionIssuanceReceipt{}, identityVerificationStoreUnavailable()
		}
		refreshToken, err = store.sessionTokens.issueRefresh()
		if err != nil {
			sessionToken.bearer = ""
			return IdentityVerificationResultDTO{}, IdentitySessionIssuanceReceipt{}, identityVerificationStoreUnavailable()
		}
	}
	idempotencyParts := []string{
		"completion-idempotency", command.ChallengeID, string(command.Purpose),
		command.AccountID, command.ActorID,
	}
	requestParts := []string{
		"completion-request", command.ChallengeID, command.CandidateCodeDigest,
		command.IdentifierDigest, string(command.Channel), string(command.Purpose),
		command.AccountID, command.DisplayName,
	}
	if issueSession {
		idempotencyParts = append(
			idempotencyParts,
			sessionToken.keyVersion,
			sessionToken.digest,
			refreshToken.keyVersion,
			refreshToken.digest,
		)
		requestParts = append(
			requestParts,
			sessionToken.keyVersion,
			sessionToken.digest,
			refreshToken.keyVersion,
			refreshToken.digest,
		)
	}
	idempotencyDigest := store.digest(idempotencyParts...)
	requestDigest := store.digest(requestParts...)
	mutationResult, err := coordinator.applyIdentityMutationTx(
		operationCtx, tx, command, receipt, receiptDigest,
		idempotencyDigest, requestDigest, mutationEventDigest, metadata,
		sessionToken.digest, refreshToken.digest,
	)
	if err != nil {
		return IdentityVerificationResultDTO{}, IdentitySessionIssuanceReceipt{}, err
	}
	if err := tx.Commit(); err != nil {
		return IdentityVerificationResultDTO{}, IdentitySessionIssuanceReceipt{}, identityVerificationStoreUnavailable()
	}

	result := IdentityVerificationResultDTO{
		SchemaVersion: IdentityVerificationSchemaVersion,
		ChallengeID:   command.ChallengeID,
		Channel:       command.Channel,
		Purpose:       command.Purpose,
		TenantID:      command.TenantID,
		Account: IdentityAccountDTO{
			SchemaVersion: UnifiedIdentitySchemaVersion,
			AccountID:     mutationResult.PrincipalID,
			PrimaryID:     mutationResult.PrincipalID,
			DisplayName:   command.DisplayName,
			Status:        "active",
		},
		Credential: IdentityCredentialDTO{
			SchemaVersion: UnifiedIdentitySchemaVersion,
			CredentialID:  mutationResult.CredentialID,
			Kind:          command.CredentialKind,
			Provider:      IdentityProviderLocal,
			Verified:      true,
			CanLogin:      true,
			LinkedAt:      command.VerifiedAt,
		},
		Created: command.Purpose == IdentityVerificationRegistration ||
			command.Purpose == IdentityVerificationBinding,
		VerifiedAt: command.VerifiedAt,
	}
	if !issueSession {
		return result, IdentitySessionIssuanceReceipt{}, nil
	}
	issuance := newIdentitySessionIssuanceReceiptWithRefresh(
		mutationResult.SessionID,
		sessionToken.keyVersion,
		refreshToken.keyVersion,
		command.SessionExpiresAt.UTC(),
		command.RefreshExpiresAt.UTC(),
		sessionToken.bearer,
		refreshToken.bearer,
	)
	sessionToken.bearer = ""
	refreshToken.bearer = ""
	return result, issuance, nil
}

func (store *PostgresIdentityVerificationStore) verifyIdentityVerificationAttemptTx(
	ctx context.Context,
	tx *sql.Tx,
	proof PostgresIdentityVerificationProof,
	receiptDigest string,
	eventDigest string,
) (PostgresIdentityVerificationReceipt, error) {
	metadata, err := marshalPostgresIdentityVerificationMetadata(proof.Metadata)
	if err != nil {
		return PostgresIdentityVerificationReceipt{}, invalidPostgresIdentityVerificationProof()
	}
	var receipt PostgresIdentityVerificationReceipt
	var databaseChallengeID, databaseReceiptID, principalID sql.NullString
	var channel, purpose sql.NullString
	err = tx.QueryRowContext(ctx, `
SELECT outcome_code,
       challenge_id::text,
       receipt_id::text,
       principal_id::text,
       channel,
       purpose,
       attempts_remaining
  FROM a1_verify_identity_verification_attempt(
    $1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8::jsonb
  )
`,
		store.organizationID,
		store.projectID,
		store.challengeDigest(proof.ChallengeID),
		proof.CandidateCodeDigest,
		proof.RequestContextDigest,
		receiptDigest,
		eventDigest,
		string(metadata),
	).Scan(
		&receipt.OutcomeCode,
		&databaseChallengeID,
		&databaseReceiptID,
		&principalID,
		&channel,
		&purpose,
		&receipt.AttemptsRemaining,
	)
	if err != nil {
		return PostgresIdentityVerificationReceipt{}, identityVerificationStoreUnavailable()
	}
	if receipt.OutcomeCode != "verified" {
		return PostgresIdentityVerificationReceipt{}, IdentityVerificationError{
			Code: "verification_rejected", Message: "verification proof was rejected",
		}
	}
	if !databaseChallengeID.Valid || !databaseReceiptID.Valid ||
		!validPostgresIdentityVerificationUUID(databaseChallengeID.String) ||
		!validPostgresIdentityVerificationUUID(databaseReceiptID.String) ||
		!channel.Valid || !purpose.Valid {
		return PostgresIdentityVerificationReceipt{}, identityVerificationStoreUnavailable()
	}
	receipt.ChallengeID = proof.ChallengeID
	receipt.ReceiptID = databaseReceiptID.String
	receipt.Channel = IdentityVerificationChannel(channel.String)
	receipt.Purpose, err = identityVerificationPurposeFromPostgres(purpose.String)
	if err != nil {
		return PostgresIdentityVerificationReceipt{}, identityVerificationStoreUnavailable()
	}
	if principalID.Valid {
		if !validPostgresIdentityVerificationUUID(principalID.String) {
			return PostgresIdentityVerificationReceipt{}, identityVerificationStoreUnavailable()
		}
		receipt.PrincipalID = principalID.String
	}
	return receipt, nil
}

type postgresIdentityVerificationMutationResult struct {
	SessionID    string
	PrincipalID  string
	CredentialID string
	ResultID     string
}

func (coordinator *PostgresIdentityVerificationTransactionCoordinator) applyIdentityMutationTx(
	ctx context.Context,
	tx *sql.Tx,
	command IdentityVerificationCompletionCommand,
	receipt PostgresIdentityVerificationReceipt,
	receiptDigest string,
	idempotencyDigest string,
	requestDigest string,
	eventDigest string,
	metadata []byte,
	sessionDigest string,
	refreshDigest string,
) (postgresIdentityVerificationMutationResult, error) {
	store := coordinator.store
	var result postgresIdentityVerificationMutationResult
	switch command.Purpose {
	case IdentityVerificationBinding:
		if !validPostgresIdentityVerificationDigest(command.SessionDigest) ||
			!validPostgresIdentityVerificationDigest(command.MutationTicketID) ||
			!validPostgresIdentityVerificationDigest(command.StepUpReceiptID) {
			return postgresIdentityVerificationMutationResult{}, invalidPostgresIdentityVerificationProof()
		}
		err := tx.QueryRowContext(ctx, `
SELECT a1_bind_verified_identity_credential_authorized(
  $1::uuid, $2::uuid, $3, $4::uuid, $5, $6, $7, $8, $9, $10, $11::jsonb
)::text
`,
			store.organizationID, store.projectID, receiptDigest,
			command.AccountID, command.SessionDigest, command.MutationTicketID,
			command.StepUpReceiptID, idempotencyDigest, requestDigest,
			eventDigest, string(metadata),
		).Scan(&result.ResultID)
		if err != nil {
			return postgresIdentityVerificationMutationResult{}, mapPostgresIdentityVerificationMutationError(err)
		}
		result.PrincipalID = command.AccountID
		result.CredentialID = result.ResultID
	case IdentityVerificationRegistration, IdentityVerificationLogin, IdentityVerificationRecovery:
		if !validPostgresIdentityVerificationDigest(sessionDigest) ||
			!validPostgresIdentityVerificationDigest(refreshDigest) ||
			sessionDigest == refreshDigest {
			return postgresIdentityVerificationMutationResult{}, invalidPostgresIdentityVerificationProof()
		}
		rotationDigest, err := store.uniqueDigest("rotation-family", command.ChallengeID)
		if err != nil {
			return postgresIdentityVerificationMutationResult{}, identityVerificationStoreUnavailable()
		}
		functionName := "a1_login_with_verified_identity_with_refresh_result"
		if command.Purpose == IdentityVerificationRegistration {
			functionName = "a1_register_with_verified_identity_with_refresh"
		} else if command.Purpose == IdentityVerificationRecovery {
			functionName = "a1_recover_verified_identity_with_refresh_result"
		}
		query := fmt.Sprintf(`
SELECT session_id::text, principal_id::text, credential_id::text
  FROM %s(
  $1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb
`, functionName)
		args := []any{
			store.organizationID, store.projectID, receiptDigest,
			sessionDigest, refreshDigest, rotationDigest,
			command.SessionExpiresAt.UTC(), command.RefreshExpiresAt.UTC(),
			idempotencyDigest, requestDigest, eventDigest,
		}
		if command.Purpose == IdentityVerificationRegistration {
			query = fmt.Sprintf(`
SELECT session_id::text, principal_id::text, credential_id::text
  FROM %s(
  $1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb
)
`, functionName)
			args = append(args, command.DisplayName, string(metadata))
		} else {
			query += ")\n"
			args = append(args, string(metadata))
		}
		err = tx.QueryRowContext(ctx, query, args...).Scan(
			&result.SessionID, &result.PrincipalID, &result.CredentialID,
		)
		if err != nil {
			return postgresIdentityVerificationMutationResult{}, mapPostgresIdentityVerificationMutationError(err)
		}
		result.ResultID = result.SessionID
	default:
		return postgresIdentityVerificationMutationResult{}, invalidPostgresIdentityVerificationProof()
	}
	if !validPostgresIdentityVerificationUUID(result.PrincipalID) ||
		!validPostgresIdentityVerificationUUID(result.CredentialID) ||
		(command.Purpose != IdentityVerificationBinding &&
			!validPostgresIdentityVerificationUUID(result.SessionID)) ||
		(command.Purpose == IdentityVerificationBinding &&
			!validPostgresIdentityVerificationUUID(result.ResultID)) {
		return postgresIdentityVerificationMutationResult{}, identityVerificationStoreUnavailable()
	}
	return result, nil
}

func validatePostgresIdentityVerificationCompletion(
	command IdentityVerificationCompletionCommand,
	store *PostgresIdentityVerificationStore,
) error {
	if !validPostgresIdentityVerificationHandle(strings.TrimSpace(command.ChallengeID), "ivc_", 256) ||
		!validPostgresIdentityVerificationDigest(command.CandidateCodeDigest) ||
		!validPostgresIdentityVerificationDigest(command.IdentifierDigest) ||
		command.TenantID != store.organizationID ||
		(command.Channel != IdentityVerificationEmail && command.Channel != IdentityVerificationPhone) ||
		(command.CredentialKind != IdentityCredentialEmail && command.CredentialKind != IdentityCredentialPhone) {
		return invalidPostgresIdentityVerificationProof()
	}
	if command.Purpose == IdentityVerificationBinding {
		if !validPostgresIdentityVerificationUUID(command.AccountID) {
			return IdentityVerificationError{
				Code:    "account_binding_required",
				Message: "production credential binding requires an existing account_id",
			}
		}
		if command.ActorID != command.AccountID ||
			!validPostgresIdentityVerificationDigest(command.SessionDigest) ||
			!validPostgresIdentityVerificationDigest(command.MutationTicketID) ||
			!validPostgresIdentityVerificationDigest(command.StepUpReceiptID) {
			return IdentityVerificationError{
				Code:    "credential_binding_authorization_required",
				Message: "production credential binding requires trusted recent authentication and step-up authorization",
			}
		}
	} else if command.Purpose == IdentityVerificationRegistration {
		if command.Channel != IdentityVerificationEmail ||
			command.CredentialKind != IdentityCredentialEmail ||
			command.AccountID != "" {
			return invalidPostgresIdentityVerificationProof()
		}
	} else if command.Purpose == IdentityVerificationLogin {
		if command.AccountID != "" &&
			!validPostgresIdentityVerificationUUID(command.AccountID) {
			return invalidPostgresIdentityVerificationProof()
		}
	} else if command.Purpose == IdentityVerificationRecovery {
		if !validPostgresIdentityVerificationUUID(command.AccountID) {
			return IdentityVerificationError{
				Code:    "account_binding_required",
				Message: "production recovery verification requires an existing account_id",
			}
		}
	} else {
		return invalidPostgresIdentityVerificationProof()
	}
	if command.SessionExpiresAt.IsZero() || !command.SessionExpiresAt.After(command.VerifiedAt) ||
		command.RefreshExpiresAt.IsZero() ||
		!command.RefreshExpiresAt.After(command.SessionExpiresAt) {
		return invalidPostgresIdentityVerificationProof()
	}
	return nil
}

func mapPostgresIdentityVerificationMutationError(error) error {
	return IdentityVerificationError{
		Code:    "verification_mutation_rejected",
		Message: "verified identity mutation was rejected",
	}
}

// RequestContextDigest returns the exact digest used when issuing a challenge.
// A production coordinator can reconstruct it without reading protected tables.
func (store *PostgresIdentityVerificationStore) RequestContextDigest(
	challenge IdentityVerificationChallenge,
) (string, error) {
	if store == nil || len(store.digestKey) < minPostgresIdentityVerificationDigestKey {
		return "", identityVerificationStoreUnavailable()
	}
	if err := validatePostgresIdentityVerificationChallengeShape(challenge); err != nil {
		return "", err
	}
	return store.requestContextDigest(challenge), nil
}

func (store *PostgresIdentityVerificationStore) Close() {
	if store == nil {
		return
	}
	for index := range store.digestKey {
		store.digestKey[index] = 0
	}
}

func (store *PostgresIdentityVerificationStore) validateChallenge(
	challenge IdentityVerificationChallenge,
	resendCooldown time.Duration,
) error {
	if err := validatePostgresIdentityVerificationChallengeShape(challenge); err != nil {
		return err
	}
	if challenge.TenantID != store.organizationID ||
		(challenge.AccountID != "" && challenge.AccountID != store.principalID) {
		return invalidPostgresIdentityVerificationChallenge()
	}
	switch challenge.Purpose {
	case IdentityVerificationRegistration:
		if challenge.Channel != IdentityVerificationEmail || challenge.AccountID != "" {
			return invalidPostgresIdentityVerificationChallenge()
		}
	case IdentityVerificationLogin:
		if challenge.AccountID != "" && store.principalID == "" {
			return invalidPostgresIdentityVerificationChallenge()
		}
	case IdentityVerificationBinding, IdentityVerificationRecovery:
		if challenge.AccountID == "" || store.principalID == "" {
			return invalidPostgresIdentityVerificationChallenge()
		}
	default:
		return invalidPostgresIdentityVerificationChallenge()
	}
	ttl := challenge.ExpiresAt.Sub(challenge.CreatedAt)
	if challenge.AttemptCount != 0 || challenge.AttemptCap < 1 || challenge.AttemptCap > 10 ||
		challenge.ConsumedAt != nil || ttl <= 0 || ttl > maxPostgresIdentityVerificationTTL ||
		resendCooldown < time.Second || resendCooldown > time.Hour ||
		resendCooldown%time.Second != 0 {
		return invalidPostgresIdentityVerificationChallenge()
	}
	return nil
}

func validatePostgresIdentityVerificationChallengeShape(
	challenge IdentityVerificationChallenge,
) error {
	if !validPostgresIdentityVerificationHandle(challenge.ChallengeID, "ivc_", 256) ||
		!validPostgresIdentityVerificationDigest(challenge.IdentifierDigest) ||
		!validPostgresIdentityVerificationDigest(challenge.CodeDigest) ||
		!validPostgresIdentityVerificationUUID(challenge.TenantID) ||
		(challenge.AccountID != "" && !validPostgresIdentityVerificationUUID(challenge.AccountID)) ||
		challenge.CreatedAt.IsZero() || !challenge.ExpiresAt.After(challenge.CreatedAt) {
		return invalidPostgresIdentityVerificationChallenge()
	}
	switch challenge.Channel {
	case IdentityVerificationEmail, IdentityVerificationPhone:
	default:
		return invalidPostgresIdentityVerificationChallenge()
	}
	switch challenge.Purpose {
	case IdentityVerificationRegistration, IdentityVerificationBinding, IdentityVerificationLogin, IdentityVerificationRecovery:
	default:
		return invalidPostgresIdentityVerificationChallenge()
	}
	return nil
}

func setPostgresIdentityVerificationScope(
	ctx context.Context,
	tx *sql.Tx,
	organizationID string,
	projectID string,
) error {
	_, err := tx.ExecContext(ctx, `
SELECT set_config('app.a1_organization_id', $1, true),
       set_config('app.a1_project_id', $2, true)
`, organizationID, projectID)
	return err
}

func (store *PostgresIdentityVerificationStore) boundedContext(
	parent context.Context,
) (context.Context, context.CancelFunc) {
	if parent == nil {
		parent = context.Background()
	}
	return context.WithTimeout(parent, store.operationTimeout)
}

func (store *PostgresIdentityVerificationStore) challengeDigest(challengeID string) string {
	return store.digest("challenge", challengeID)
}

func (store *PostgresIdentityVerificationStore) requestContextDigest(
	challenge IdentityVerificationChallenge,
) string {
	return store.digest(
		"request-context",
		store.organizationID,
		store.projectID,
		store.challengePrincipalID(challenge),
		string(challenge.Channel),
		postgresIdentityVerificationPurpose(challenge.Purpose),
		challenge.IdentifierDigest,
	)
}

func (store *PostgresIdentityVerificationStore) challengePrincipalID(
	challenge IdentityVerificationChallenge,
) string {
	if challenge.Purpose == IdentityVerificationRegistration ||
		(challenge.Purpose == IdentityVerificationLogin && challenge.AccountID == "") {
		return ""
	}
	return store.principalID
}

func (store *PostgresIdentityVerificationStore) uniqueDigest(
	purpose string,
	challengeID string,
) (string, error) {
	nonce := make([]byte, 24)
	if _, err := io.ReadFull(store.random, nonce); err != nil {
		return "", err
	}
	return store.digest(purpose, challengeID, hex.EncodeToString(nonce)), nil
}

func (store *PostgresIdentityVerificationStore) digest(parts ...string) string {
	mac := hmac.New(sha256.New, store.digestKey)
	for _, part := range parts {
		_, _ = mac.Write([]byte(part))
		_, _ = mac.Write([]byte{0})
	}
	return hex.EncodeToString(mac.Sum(nil))
}

func postgresIdentityVerificationPurpose(purpose IdentityVerificationPurpose) string {
	switch purpose {
	case IdentityVerificationRegistration:
		return "registration"
	case IdentityVerificationBinding:
		return "credential_binding"
	case IdentityVerificationRecovery:
		return "account_recovery"
	default:
		return string(purpose)
	}
}

func identityVerificationPurposeFromPostgres(
	purpose string,
) (IdentityVerificationPurpose, error) {
	switch purpose {
	case "registration":
		return IdentityVerificationRegistration, nil
	case "credential_binding":
		return IdentityVerificationBinding, nil
	case "login":
		return IdentityVerificationLogin, nil
	case "account_recovery":
		return IdentityVerificationRecovery, nil
	default:
		return "", errors.New("unsupported PostgreSQL identity verification purpose")
	}
}

func marshalPostgresIdentityVerificationMetadata(metadata map[string]any) ([]byte, error) {
	if metadata == nil {
		return []byte(`{}`), nil
	}
	encoded, err := json.Marshal(metadata)
	if err != nil || len(encoded) > 8192 {
		return nil, errors.New("invalid identity verification metadata")
	}
	return encoded, nil
}

func validPostgresIdentityVerificationHandle(value, prefix string, maxLength int) bool {
	if len(value) <= len(prefix) || len(value) > maxLength || !strings.HasPrefix(value, prefix) {
		return false
	}
	for _, character := range value[len(prefix):] {
		if (character < 'a' || character > 'z') &&
			(character < 'A' || character > 'Z') &&
			(character < '0' || character > '9') &&
			character != '_' && character != '-' {
			return false
		}
	}
	return true
}

func validPostgresIdentityVerificationDigest(value string) bool {
	if len(value) != sha256.Size*2 || strings.ToLower(value) != value {
		return false
	}
	decoded, err := hex.DecodeString(value)
	return err == nil && len(decoded) == sha256.Size
}

func validPostgresIdentityVerificationUUID(value string) bool {
	return postgresIdentityVerificationUUIDPattern.MatchString(value)
}

func invalidPostgresIdentityVerificationChallenge() IdentityVerificationError {
	return IdentityVerificationError{
		Code:    "invalid_verification_challenge",
		Message: "identity verification challenge is invalid",
	}
}

func invalidPostgresIdentityVerificationProof() IdentityVerificationError {
	return IdentityVerificationError{
		Code:    "invalid_verification_proof",
		Message: "verification proof is invalid",
	}
}

func identityVerificationStoreUnavailable() IdentityVerificationError {
	return IdentityVerificationError{
		Code:    "verification_store_unavailable",
		Message: "identity verification is temporarily unavailable",
	}
}

var (
	_ IdentityVerificationStore                            = (*PostgresIdentityVerificationStore)(nil)
	_ ProductionIdentityVerificationStore                  = (*PostgresIdentityVerificationStore)(nil)
	_ ProductionIdentityVerificationOutboxStore            = (*PostgresIdentityVerificationStore)(nil)
	_ ProductionIdentityVerificationTransactionCoordinator = (*PostgresIdentityVerificationTransactionCoordinator)(nil)
	_ IdentityVerificationSessionTransactionCoordinator    = (*PostgresIdentityVerificationTransactionCoordinator)(nil)
)
