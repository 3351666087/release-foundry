package ashrclone

import (
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/lib/pq"
)

const defaultIdentityLifecycleKeyVersion = "v1"

var ErrIdentityProofKeyUnavailable = errors.New("identity proof receipt key version unavailable")

type identityLifecycleKeyring struct {
	mu           sync.RWMutex
	active       string
	keys         map[string][]byte
	lookupActive string
	lookupKeys   map[string][]byte
	random       io.Reader
}

func newIdentityLifecycleKeyring(
	active string,
	key []byte,
	previous []IdentityLifecycleEncryptionKey,
) (*identityLifecycleKeyring, error) {
	return newIdentityLifecycleKeyringWithLookup(
		active, key, previous, "", nil, nil,
	)
}

func newIdentityLifecycleKeyringWithLookup(
	active string,
	key []byte,
	previous []IdentityLifecycleEncryptionKey,
	lookupActive string,
	lookupKey []byte,
	previousLookup []IdentityLifecycleLookupKey,
) (*identityLifecycleKeyring, error) {
	explicitLookup := strings.TrimSpace(lookupActive) != "" ||
		len(lookupKey) != 0 ||
		len(previousLookup) != 0
	if len(key) == 0 && len(previous) == 0 {
		if explicitLookup {
			return nil, fmt.Errorf("production identity lifecycle lookup key requires a receipt encryption keyring")
		}
		return nil, nil
	}
	if len(key) < 32 {
		return nil, fmt.Errorf("production identity lifecycle receipt key must be at least 32 bytes")
	}
	active = strings.TrimSpace(active)
	if active == "" {
		active = defaultIdentityLifecycleKeyVersion
	}
	if !validIdentitySessionKeyVersion(active) {
		return nil, fmt.Errorf("production identity lifecycle key version is invalid")
	}
	keys := map[string][]byte{active: append([]byte(nil), key...)}
	for _, item := range previous {
		version := strings.TrimSpace(item.Version)
		if !validIdentitySessionKeyVersion(version) || len(item.Key) < 32 {
			closeIdentityLifecycleKeys(keys)
			return nil, fmt.Errorf("production identity previous lifecycle key is invalid")
		}
		if _, exists := keys[version]; exists {
			closeIdentityLifecycleKeys(keys)
			return nil, fmt.Errorf("production identity lifecycle key version %q is duplicated", version)
		}
		keys[version] = append([]byte(nil), item.Key...)
	}
	lookupKeys := make(map[string][]byte)
	if !explicitLookup {
		lookupActive = active
		for version, item := range keys {
			lookupKeys[version] = append([]byte(nil), item...)
		}
	} else {
		lookupActive = strings.TrimSpace(lookupActive)
		if !validIdentitySessionKeyVersion(lookupActive) || len(lookupKey) < 32 {
			closeIdentityLifecycleKeys(keys)
			return nil, fmt.Errorf("production identity lifecycle lookup key is invalid")
		}
		lookupKeys[lookupActive] = append([]byte(nil), lookupKey...)
		for _, item := range previousLookup {
			version := strings.TrimSpace(item.Version)
			if !validIdentitySessionKeyVersion(version) || len(item.Key) < 32 {
				closeIdentityLifecycleKeys(keys)
				closeIdentityLifecycleKeys(lookupKeys)
				return nil, fmt.Errorf("production identity previous lifecycle lookup key is invalid")
			}
			if _, exists := lookupKeys[version]; exists {
				closeIdentityLifecycleKeys(keys)
				closeIdentityLifecycleKeys(lookupKeys)
				return nil, fmt.Errorf("production identity lifecycle lookup key version %q is duplicated", version)
			}
			lookupKeys[version] = append([]byte(nil), item.Key...)
		}
	}
	return &identityLifecycleKeyring{
		active: active, keys: keys,
		lookupActive: lookupActive, lookupKeys: lookupKeys,
		random: rand.Reader,
	}, nil
}

func (ring *identityLifecycleKeyring) clone() *identityLifecycleKeyring {
	if ring == nil {
		return nil
	}
	ring.mu.RLock()
	defer ring.mu.RUnlock()
	keys := make(map[string][]byte, len(ring.keys))
	for version, key := range ring.keys {
		keys[version] = append([]byte(nil), key...)
	}
	lookupKeys := make(map[string][]byte, len(ring.lookupKeys))
	for version, key := range ring.lookupKeys {
		lookupKeys[version] = append([]byte(nil), key...)
	}
	return &identityLifecycleKeyring{
		active: ring.active, keys: keys,
		lookupActive: ring.lookupActive, lookupKeys: lookupKeys,
		random: ring.random,
	}
}

func (ring *identityLifecycleKeyring) close() {
	if ring == nil {
		return
	}
	ring.mu.Lock()
	defer ring.mu.Unlock()
	closeIdentityLifecycleKeys(ring.keys)
	closeIdentityLifecycleKeys(ring.lookupKeys)
}

func closeIdentityLifecycleKeys(keys map[string][]byte) {
	for _, key := range keys {
		for index := range key {
			key[index] = 0
		}
	}
}

type identityLifecycleReceiptMetadata struct {
	Digest        string
	Operation     IdentityLifecycleOperation
	Provider      IdentityProvider
	TenantScope   string
	ProjectScope  string
	ExpiresAt     time.Time
	SchemaVersion string
	KeyVersion    string
}

func (metadata identityLifecycleReceiptMetadata) aad() []byte {
	values := []string{
		metadata.Digest,
		string(metadata.Operation),
		string(metadata.Provider),
		metadata.TenantScope,
		metadata.ProjectScope,
		metadata.ExpiresAt.UTC().Format(time.RFC3339Nano),
		metadata.SchemaVersion,
		metadata.KeyVersion,
	}
	return []byte(strings.Join(values, "\x00"))
}

func (ring *identityLifecycleKeyring) receiptDigest(raw string) string {
	ring.mu.RLock()
	defer ring.mu.RUnlock()
	mac := hmac.New(sha256.New, ring.lookupKeys[ring.lookupActive])
	_, _ = mac.Write([]byte(strings.TrimSpace(raw)))
	return hex.EncodeToString(mac.Sum(nil))
}

func (ring *identityLifecycleKeyring) receiptDigests(raw string) []string {
	ring.mu.RLock()
	defer ring.mu.RUnlock()
	raw = strings.TrimSpace(raw)
	versions := make([]string, 1, len(ring.lookupKeys))
	versions[0] = ring.lookupActive
	for version := range ring.lookupKeys {
		if version != ring.lookupActive {
			versions = append(versions, version)
		}
	}
	sort.Strings(versions[1:])
	digests := make([]string, 0, len(versions))
	seen := make(map[string]struct{}, len(versions))
	for _, version := range versions {
		mac := hmac.New(sha256.New, ring.lookupKeys[version])
		_, _ = mac.Write([]byte(raw))
		digest := hex.EncodeToString(mac.Sum(nil))
		if _, exists := seen[digest]; exists {
			continue
		}
		seen[digest] = struct{}{}
		digests = append(digests, digest)
	}
	return digests
}

func (ring *identityLifecycleKeyring) seal(
	metadata identityLifecycleReceiptMetadata,
	proof TrustedIdentityProof,
) ([]byte, []byte, error) {
	ring.mu.RLock()
	defer ring.mu.RUnlock()
	key := ring.keys[metadata.KeyVersion]
	if len(key) < 32 {
		return nil, nil, ErrIdentityProofKeyUnavailable
	}
	block, err := aes.NewCipher(key[:32])
	if err != nil {
		return nil, nil, err
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, nil, err
	}
	nonce := make([]byte, aead.NonceSize())
	if _, err := io.ReadFull(ring.random, nonce); err != nil {
		return nil, nil, err
	}
	plain, err := json.Marshal(proof)
	if err != nil {
		return nil, nil, err
	}
	defer func() {
		for index := range plain {
			plain[index] = 0
		}
	}()
	return nonce, aead.Seal(nil, nonce, plain, metadata.aad()), nil
}

func (ring *identityLifecycleKeyring) open(
	metadata identityLifecycleReceiptMetadata,
	nonce, ciphertext []byte,
) (TrustedIdentityProof, error) {
	ring.mu.RLock()
	defer ring.mu.RUnlock()
	key := ring.keys[metadata.KeyVersion]
	if len(key) < 32 {
		return TrustedIdentityProof{}, ErrIdentityProofKeyUnavailable
	}
	block, err := aes.NewCipher(key[:32])
	if err != nil {
		return TrustedIdentityProof{}, err
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return TrustedIdentityProof{}, err
	}
	plain, err := aead.Open(nil, nonce, ciphertext, metadata.aad())
	if err != nil {
		return TrustedIdentityProof{}, fmt.Errorf("open identity proof receipt: %w", err)
	}
	defer func() {
		for index := range plain {
			plain[index] = 0
		}
	}()
	var proof TrustedIdentityProof
	if err := json.Unmarshal(plain, &proof); err != nil {
		return TrustedIdentityProof{}, fmt.Errorf("decode identity proof receipt: %w", err)
	}
	return proof, nil
}

type postgresIdentityLifecycleReceiptStore struct {
	db               *sql.DB
	keys             *identityLifecycleKeyring
	sqlTimeout       time.Duration
	statementTimeout time.Duration
	lockTimeout      time.Duration
}

func (*postgresIdentityLifecycleReceiptStore) ProductionDurable() bool { return true }

func (store *postgresIdentityLifecycleReceiptStore) receiptDigest(raw string) string {
	return store.keys.receiptDigest(raw)
}

func (store *postgresIdentityLifecycleReceiptStore) Issue(
	ctx context.Context,
	dto IdentityProofReceiptDTO,
	proof TrustedIdentityProof,
) error {
	digest := store.receiptDigest(dto.ReceiptID)
	metadata := identityLifecycleReceiptMetadata{
		Digest: digest, Operation: dto.Operation, Provider: normalizeIdentityLifecycleProvider(dto.Provider),
		TenantScope: strings.TrimSpace(dto.TenantID), ProjectScope: strings.TrimSpace(dto.ProjectID),
		ExpiresAt: dto.ExpiresAt.UTC(), SchemaVersion: IdentityLifecycleSchemaVersion,
		KeyVersion: store.keys.active,
	}
	nonce, ciphertext, err := store.keys.seal(metadata, proof)
	if err != nil {
		return fmt.Errorf("seal identity lifecycle proof: %w", err)
	}
	operationCtx, cancel := context.WithTimeout(ctx, store.sqlTimeout)
	defer cancel()
	_, err = store.db.ExecContext(operationCtx, `
SELECT a1_issue_identity_lifecycle_receipt($1,$2,$3,$4,$5,$6,$7,$8,$9)
`, metadata.Digest, metadata.Operation, metadata.Provider, metadata.TenantScope,
		metadata.ProjectScope, nonce, metadata.KeyVersion, ciphertext, metadata.ExpiresAt)
	if err != nil {
		return fmt.Errorf("persist identity lifecycle receipt: %w", err)
	}
	return nil
}

func (store *postgresIdentityLifecycleReceiptStore) Consume(
	ctx context.Context,
	request CompleteIdentityLifecycleRequest,
	operation IdentityLifecycleOperation,
	now time.Time,
) (TrustedIdentityProof, error) {
	operationCtx, cancel := context.WithTimeout(ctx, store.sqlTimeout)
	defer cancel()
	tx, err := store.db.BeginTx(operationCtx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return TrustedIdentityProof{}, err
	}
	defer tx.Rollback()
	if err := configureIdentityLifecycleTx(operationCtx, tx, store.statementTimeout, store.lockTimeout); err != nil {
		return TrustedIdentityProof{}, err
	}
	locked, err := store.lockReceipt(operationCtx, tx, request, operation, now)
	if err != nil {
		return TrustedIdentityProof{}, err
	}
	if err := consumeIdentityLifecycleReceipt(operationCtx, tx, locked.metadata, now); err != nil {
		return TrustedIdentityProof{}, err
	}
	if err := tx.Commit(); err != nil {
		return TrustedIdentityProof{}, err
	}
	return locked.proof, nil
}

type lockedIdentityLifecycleReceipt struct {
	metadata identityLifecycleReceiptMetadata
	proof    TrustedIdentityProof
}

func (store *postgresIdentityLifecycleReceiptStore) lockReceipt(
	ctx context.Context,
	tx *sql.Tx,
	request CompleteIdentityLifecycleRequest,
	operation IdentityLifecycleOperation,
	now time.Time,
) (lockedIdentityLifecycleReceipt, error) {
	digests := store.keys.receiptDigests(request.ReceiptID)
	var metadata identityLifecycleReceiptMetadata
	var nonce, ciphertext []byte
	var consumedAt sql.NullTime
	metadata.SchemaVersion = IdentityLifecycleSchemaVersion
	err := tx.QueryRowContext(ctx, `
SELECT receipt_digest, operation, provider, tenant_scope, project_scope, expires_at,
       consumed_at, proof_nonce, proof_key_version, proof_ciphertext
FROM a1_lock_identity_lifecycle_receipt($1)
`, pq.Array(digests)).Scan(
		&metadata.Digest, &metadata.Operation, &metadata.Provider, &metadata.TenantScope, &metadata.ProjectScope,
		&metadata.ExpiresAt, &consumedAt, &nonce, &metadata.KeyVersion, &ciphertext,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return lockedIdentityLifecycleReceipt{}, ErrIdentityProofReceiptNotFound
	}
	if err != nil {
		return lockedIdentityLifecycleReceipt{}, err
	}
	if consumedAt.Valid {
		return lockedIdentityLifecycleReceipt{}, ErrIdentityProofReceiptConsumed
	}
	if !now.UTC().Before(metadata.ExpiresAt.UTC()) {
		return lockedIdentityLifecycleReceipt{}, ErrIdentityProofReceiptExpired
	}
	if metadata.Operation != operation ||
		metadata.Provider != normalizeIdentityLifecycleProvider(request.Provider) ||
		metadata.TenantScope != strings.TrimSpace(request.TenantID) ||
		metadata.ProjectScope != strings.TrimSpace(request.ProjectID) {
		return lockedIdentityLifecycleReceipt{}, ErrIdentityProofScopeMismatch
	}
	proof, err := store.keys.open(metadata, nonce, ciphertext)
	if err != nil {
		return lockedIdentityLifecycleReceipt{}, err
	}
	return lockedIdentityLifecycleReceipt{metadata: metadata, proof: proof}, nil
}

func configureIdentityLifecycleTx(
	ctx context.Context,
	tx *sql.Tx,
	statementTimeout, lockTimeout time.Duration,
) error {
	_, err := tx.ExecContext(ctx, `
SELECT set_config('statement_timeout', $1, true), set_config('lock_timeout', $2, true)
`, fmt.Sprintf("%dms", statementTimeout.Milliseconds()), fmt.Sprintf("%dms", lockTimeout.Milliseconds()))
	return err
}

func consumeIdentityLifecycleReceipt(
	ctx context.Context,
	tx *sql.Tx,
	metadata identityLifecycleReceiptMetadata,
	now time.Time,
) error {
	var consumed bool
	err := tx.QueryRowContext(ctx, `
SELECT a1_consume_identity_lifecycle_receipt($1,$2,$3,$4,$5,$6)
`, metadata.Digest, metadata.Operation, metadata.Provider, metadata.TenantScope,
		metadata.ProjectScope, now.UTC()).Scan(&consumed)
	if err != nil {
		return err
	}
	if !consumed {
		return ErrIdentityProofReceiptConsumed
	}
	return nil
}

type PostgresIdentityLifecycleTransactionCoordinator struct {
	store      *ProductionIdentityStore
	receipts   *postgresIdentityLifecycleReceiptStore
	sessionTTL time.Duration
}

func NewPostgresIdentityLifecycleTransactionCoordinator(
	store *ProductionIdentityStore,
	receipts IdentityLifecycleReceiptStore,
) (*PostgresIdentityLifecycleTransactionCoordinator, error) {
	receiptStore, ok := receipts.(*postgresIdentityLifecycleReceiptStore)
	if store == nil || store.db == nil || store.sessionTokens == nil || !ok || receiptStore.db != store.db {
		return nil, fmt.Errorf("postgres identity lifecycle coordinator requires one production store and receipt database")
	}
	return &PostgresIdentityLifecycleTransactionCoordinator{
		store: store, receipts: receiptStore, sessionTTL: defaultIdentityAccessSessionTTL,
	}, nil
}

func (coordinator *PostgresIdentityLifecycleTransactionCoordinator) CompleteRegistration(
	ctx context.Context,
	request CompleteIdentityLifecycleRequest,
	now time.Time,
) (IdentityAccountDTO, error) {
	var result IdentityAccountDTO
	err := coordinator.complete(ctx, request, IdentityOperationRegistration, now, func(
		ctx context.Context, tx *sql.Tx, locked lockedIdentityLifecycleReceipt,
	) error {
		proof := locked.proof
		subjectDigests := coordinator.receipts.keys.receiptDigests(
			"credential:" + string(proof.Provider) + ":" + proof.Identifier,
		)
		var principalID, credentialID string
		kind := postgresIdentityCredentialKind(proof.Kind, proof.Provider)
		emailDigest := ""
		emailSource := ""
		if proof.VerifiedEmail != "" {
			emailDigest = coordinator.receipts.receiptDigest("email:" + strings.ToLower(strings.TrimSpace(proof.VerifiedEmail)))
			emailSource = postgresIdentityProvider(proof.Provider)
		}
		if err := tx.QueryRowContext(ctx, `
SELECT registered_principal_id::text, registered_credential_id::text
FROM a1_register_identity_lifecycle_credential($1,$2,$3,$4,NULLIF($5,''),NULLIF($6,''),$7,$8)
`, postgresIdentityProvider(proof.Provider), kind, pq.Array(subjectDigests),
			strings.TrimSpace(proof.DisplayName), emailDigest, emailSource,
			locked.metadata.Digest, now.UTC()).Scan(&principalID, &credentialID); err != nil {
			if isPostgresUniqueViolation(err) {
				return IdentityDomainError{Code: "credential_already_registered", Message: "credential is already registered"}
			}
			return err
		}
		if _, err := coordinator.issueSession(ctx, tx, principalID, credentialID, locked.metadata.Digest, now); err != nil {
			return err
		}
		projected, projectErr := coordinator.projectAccount(ctx, tx, principalID)
		if projectErr != nil {
			return projectErr
		}
		result = projected
		return nil
	})
	return result, err
}

func (coordinator *PostgresIdentityLifecycleTransactionCoordinator) CompleteLogin(
	ctx context.Context,
	request CompleteIdentityLifecycleRequest,
	now time.Time,
) (IdentityAuthenticationDTO, error) {
	var result IdentityAuthenticationDTO
	err := coordinator.complete(ctx, request, IdentityOperationLogin, now, func(
		ctx context.Context, tx *sql.Tx, locked lockedIdentityLifecycleReceipt,
	) error {
		proof := locked.proof
		subjectDigests := coordinator.receipts.keys.receiptDigests(
			"credential:" + string(proof.Provider) + ":" + proof.Identifier,
		)
		var principalID, credentialID string
		err := tx.QueryRowContext(ctx, `
SELECT authenticated_principal_id::text, authenticated_credential_id::text
FROM a1_authenticate_identity_lifecycle_credential($1,$2,$3)
`, postgresIdentityProvider(proof.Provider), pq.Array(subjectDigests), now.UTC()).
			Scan(&principalID, &credentialID)
		if errors.Is(err, sql.ErrNoRows) {
			return ErrIdentityCredentialNotFound
		}
		if err != nil {
			return err
		}
		if _, err := coordinator.issueSession(ctx, tx, principalID, credentialID, locked.metadata.Digest, now); err != nil {
			return err
		}
		account, err := coordinator.projectAccount(ctx, tx, principalID)
		if err != nil {
			return err
		}
		var authenticatedCredential IdentityCredentialDTO
		for _, credential := range account.Credentials {
			if credential.CredentialID == credentialID {
				authenticatedCredential = credential
				break
			}
		}
		if authenticatedCredential.CredentialID == "" {
			return fmt.Errorf("authenticated identity credential projection is unavailable")
		}
		result = IdentityAuthenticationDTO{
			SchemaVersion: UnifiedIdentitySchemaVersion, Account: account,
			PrincipalID: principalID, Credential: authenticatedCredential,
			Memberships: account.Memberships, Authenticated: now.UTC(),
		}
		return nil
	})
	return result, err
}

func (coordinator *PostgresIdentityLifecycleTransactionCoordinator) complete(
	ctx context.Context,
	request CompleteIdentityLifecycleRequest,
	operation IdentityLifecycleOperation,
	now time.Time,
	mutate func(context.Context, *sql.Tx, lockedIdentityLifecycleReceipt) error,
) error {
	const maxTransactionAttempts = 8
	for attempt := 0; attempt < maxTransactionAttempts; attempt++ {
		err := coordinator.completeOnce(ctx, request, operation, now, mutate)
		if !isPostgresTransactionRetryable(err) {
			return err
		}
		timer := time.NewTimer(time.Duration(attempt+1) * 5 * time.Millisecond)
		select {
		case <-ctx.Done():
			timer.Stop()
			return ctx.Err()
		case <-timer.C:
		}
	}
	return fmt.Errorf("identity lifecycle transaction remained contended after %d attempts", maxTransactionAttempts)
}

func (coordinator *PostgresIdentityLifecycleTransactionCoordinator) completeOnce(
	ctx context.Context,
	request CompleteIdentityLifecycleRequest,
	operation IdentityLifecycleOperation,
	now time.Time,
	mutate func(context.Context, *sql.Tx, lockedIdentityLifecycleReceipt) error,
) error {
	operationCtx, cancel := context.WithTimeout(ctx, coordinator.receipts.sqlTimeout)
	defer cancel()
	tx, err := coordinator.store.db.BeginTx(operationCtx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if err := configureIdentityLifecycleTx(operationCtx, tx, coordinator.receipts.statementTimeout, coordinator.receipts.lockTimeout); err != nil {
		return err
	}
	locked, err := coordinator.receipts.lockReceipt(operationCtx, tx, request, operation, now)
	if err != nil {
		return err
	}
	if err := mutate(operationCtx, tx, locked); err != nil {
		return err
	}
	if err := consumeIdentityLifecycleReceipt(operationCtx, tx, locked.metadata, now); err != nil {
		return err
	}
	return tx.Commit()
}

func (coordinator *PostgresIdentityLifecycleTransactionCoordinator) issueSession(
	ctx context.Context,
	tx *sql.Tx,
	principalID, credentialID, requestDigest string,
	now time.Time,
) (identitySessionTokenMaterial, error) {
	token, err := coordinator.store.sessionTokens.issue()
	if err != nil {
		return identitySessionTokenMaterial{}, err
	}
	rotationDigest, err := coordinator.store.sessionTokens.digestActive("identity-lifecycle", principalID, token.digest)
	if err != nil {
		return identitySessionTokenMaterial{}, err
	}
	var sessionID string
	err = tx.QueryRowContext(ctx, `
SELECT id::text FROM a1_issue_identity_session(
  $1::uuid,$2::uuid,$3,$4,$5,NULL,NULL,'aal1',$6,
  jsonb_build_object('source','identity_lifecycle','key_version',$7::text)
)
`, principalID, credentialID, token.digest, rotationDigest,
		now.UTC().Add(coordinator.sessionTTL), requestDigest, token.keyVersion).Scan(&sessionID)
	if err != nil {
		return identitySessionTokenMaterial{}, err
	}
	return token, nil
}

func postgresIdentityProvider(provider IdentityProvider) string {
	if normalizeIdentityLifecycleProvider(provider) == IdentityProviderLocal {
		return "email"
	}
	return string(normalizeIdentityLifecycleProvider(provider))
}

func postgresIdentityCredentialKind(kind IdentityCredentialKind, provider IdentityProvider) string {
	if provider == IdentityProviderLocal {
		return "email_otp"
	}
	if kind == IdentityCredentialPhone {
		return "phone_otp"
	}
	return "federated"
}

type identityLifecycleAccountProjection struct {
	PrincipalID          string                                  `json:"principal_id"`
	DisplayName          string                                  `json:"display_name"`
	Status               string                                  `json:"status"`
	CreatedAt            time.Time                               `json:"created_at"`
	UpdatedAt            time.Time                               `json:"updated_at"`
	PrimaryEmail         *identityLifecycleEmailProjection       `json:"primary_email"`
	PasswordStatus       string                                  `json:"password_status"`
	TwoFactorStatus      string                                  `json:"two_factor_status"`
	TwoFactorRecommended bool                                    `json:"two_factor_recommended"`
	Credentials          []identityLifecycleCredentialProjection `json:"credentials"`
	Memberships          []identityLifecycleMembershipProjection `json:"memberships"`
}

type identityLifecycleEmailProjection struct {
	Present        bool   `json:"present"`
	Verified       bool   `json:"verified"`
	SourceProvider string `json:"source_provider"`
}

type identityLifecycleCredentialProjection struct {
	CredentialID   string     `json:"credential_id"`
	Provider       string     `json:"provider"`
	CredentialKind string     `json:"credential_kind"`
	Verified       bool       `json:"verified"`
	CanLogin       bool       `json:"can_login"`
	LinkedAt       time.Time  `json:"linked_at"`
	LastUsedAt     *time.Time `json:"last_used_at"`
}

type identityLifecycleMembershipProjection struct {
	MembershipID string    `json:"membership_id"`
	TenantID     string    `json:"tenant_id"`
	ProjectID    string    `json:"project_id"`
	Role         string    `json:"role"`
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
}

func (projection identityLifecycleAccountProjection) toDTO() IdentityAccountDTO {
	account := IdentityAccountDTO{
		SchemaVersion: UnifiedIdentitySchemaVersion,
		AccountID:     projection.PrincipalID, PrimaryID: projection.PrincipalID,
		DisplayName: projection.DisplayName, Status: projection.Status,
		Credentials: []IdentityCredentialDTO{}, Memberships: []IdentityMembershipDTO{},
		SecurityPosture: IdentitySecurityPostureDTO{
			Password: IdentityPasswordPostureDTO{
				Status: projection.PasswordStatus, Settable: true,
			},
			TwoFactor: IdentityTwoFactorPostureDTO{
				Status: projection.TwoFactorStatus, Optional: true,
				Recommended: projection.TwoFactorRecommended,
			},
		},
		CreatedAt: projection.CreatedAt.UTC(), UpdatedAt: projection.UpdatedAt.UTC(),
	}
	if projection.PrimaryEmail != nil {
		account.SecurityPosture.PrimaryEmail = IdentityEmailPostureDTO{
			Present:  projection.PrimaryEmail.Present,
			Verified: projection.PrimaryEmail.Verified,
			Source:   publicIdentityLifecycleProvider(projection.PrimaryEmail.SourceProvider),
		}
	}
	for _, item := range projection.Credentials {
		credential := IdentityCredentialDTO{
			SchemaVersion: UnifiedIdentitySchemaVersion,
			CredentialID:  item.CredentialID,
			Provider:      publicIdentityLifecycleProvider(item.Provider),
			Verified:      item.Verified, CanLogin: item.CanLogin,
			LinkedAt: item.LinkedAt.UTC(),
		}
		credential.Kind = publicIdentityCredentialKind(item.CredentialKind, credential.Provider)
		if item.LastUsedAt != nil {
			value := item.LastUsedAt.UTC()
			credential.LastUsedAt = &value
		}
		account.Credentials = append(account.Credentials, credential)
	}
	for _, item := range projection.Memberships {
		account.Memberships = append(account.Memberships, IdentityMembershipDTO{
			SchemaVersion: UnifiedIdentitySchemaVersion,
			MembershipID:  item.MembershipID, AccountID: projection.PrincipalID,
			TenantID: item.TenantID, ProjectID: item.ProjectID, Role: item.Role,
			CreatedAt: item.CreatedAt.UTC(), UpdatedAt: item.UpdatedAt.UTC(),
		})
	}
	return account
}

func publicIdentityLifecycleProvider(provider string) IdentityProvider {
	if provider == "email" {
		return IdentityProviderLocal
	}
	return normalizeIdentityLifecycleProvider(IdentityProvider(provider))
}

func isPostgresUniqueViolation(err error) bool {
	var postgresError *pq.Error
	return errors.As(err, &postgresError) && postgresError.Code == "23505"
}

func isPostgresTransactionRetryable(err error) bool {
	var postgresError *pq.Error
	if !errors.As(err, &postgresError) {
		return false
	}
	return postgresError.Code == "40001" || postgresError.Code == "40P01"
}

func (coordinator *PostgresIdentityLifecycleTransactionCoordinator) projectAccount(
	ctx context.Context,
	tx *sql.Tx,
	principalID string,
) (IdentityAccountDTO, error) {
	var raw []byte
	if err := tx.QueryRowContext(ctx, `
SELECT a1_project_identity_lifecycle_account($1::uuid)
`, principalID).Scan(&raw); err != nil {
		return IdentityAccountDTO{}, err
	}
	var projection identityLifecycleAccountProjection
	if err := json.Unmarshal(raw, &projection); err != nil {
		return IdentityAccountDTO{}, fmt.Errorf("decode identity lifecycle account projection: %w", err)
	}
	account := projection.toDTO()
	if account.AccountID == "" {
		return IdentityAccountDTO{}, sql.ErrNoRows
	}
	account.CredentialCount = len(account.Credentials)
	account.MembershipCount = len(account.Memberships)
	return account, nil
}

func (coordinator *PostgresIdentityLifecycleTransactionCoordinator) projectMemberships(
	ctx context.Context,
	tx *sql.Tx,
	principalID string,
) ([]IdentityMembershipDTO, error) {
	rows, err := tx.QueryContext(ctx, `
SELECT id::text, organization_id::text, ''::text, role, created_at, updated_at
FROM identity_organization_memberships
WHERE principal_id=$1::uuid AND status='active'
UNION ALL
SELECT id::text, organization_id::text, project_id::text, role, created_at, updated_at
FROM identity_project_memberships
WHERE principal_id=$1::uuid AND status='active'
ORDER BY 2, 3, 1
`, principalID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := make([]IdentityMembershipDTO, 0)
	for rows.Next() {
		var membership IdentityMembershipDTO
		if err := rows.Scan(
			&membership.MembershipID, &membership.TenantID, &membership.ProjectID,
			&membership.Role, &membership.CreatedAt, &membership.UpdatedAt,
		); err != nil {
			return nil, err
		}
		membership.SchemaVersion = UnifiedIdentitySchemaVersion
		membership.AccountID = principalID
		result = append(result, membership)
	}
	return result, rows.Err()
}

func publicIdentityCredentialKind(kind string, provider IdentityProvider) IdentityCredentialKind {
	if provider == IdentityProviderLocal {
		return IdentityCredentialEmail
	}
	if kind == "phone_otp" {
		return IdentityCredentialPhone
	}
	return IdentityCredentialOAuth
}

var (
	_ IdentityLifecycleReceiptStore           = (*postgresIdentityLifecycleReceiptStore)(nil)
	_ IdentityLifecycleTransactionCoordinator = (*PostgresIdentityLifecycleTransactionCoordinator)(nil)
)
