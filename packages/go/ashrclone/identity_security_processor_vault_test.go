package ashrclone

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base32"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/url"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

const identitySecurityProcessorVaultTestAccountID = "33333333-3333-4333-8333-333333333333"

type identitySecurityProcessorVaultTestRecord struct {
	payload []byte
	version uint64
}

type identitySecurityProcessorMemoryVault struct {
	mu        sync.Mutex
	records   map[string]identitySecurityProcessorVaultTestRecord
	readyErr  error
	readErr   error
	createErr error
	swapErr   error
	deleteErr error
}

func newIdentitySecurityProcessorMemoryVault() *identitySecurityProcessorMemoryVault {
	return &identitySecurityProcessorMemoryVault{
		records: make(map[string]identitySecurityProcessorVaultTestRecord),
	}
}

func (vault *identitySecurityProcessorMemoryVault) Ready(context.Context) error {
	vault.mu.Lock()
	defer vault.mu.Unlock()
	return vault.readyErr
}

func (vault *identitySecurityProcessorMemoryVault) Read(
	_ context.Context,
	key string,
) ([]byte, uint64, error) {
	vault.mu.Lock()
	defer vault.mu.Unlock()
	if vault.readErr != nil {
		return nil, 0, vault.readErr
	}
	record, ok := vault.records[key]
	if !ok {
		return nil, 0, ErrIdentitySecurityProcessorVaultRecordNotFound
	}
	return append([]byte(nil), record.payload...), record.version, nil
}

func (vault *identitySecurityProcessorMemoryVault) Create(
	_ context.Context,
	key string,
	payload []byte,
) (bool, error) {
	vault.mu.Lock()
	defer vault.mu.Unlock()
	if vault.createErr != nil {
		return false, vault.createErr
	}
	if _, exists := vault.records[key]; exists {
		return false, nil
	}
	vault.records[key] = identitySecurityProcessorVaultTestRecord{
		payload: append([]byte(nil), payload...),
		version: 1,
	}
	return true, nil
}

func (vault *identitySecurityProcessorMemoryVault) CompareAndSwap(
	_ context.Context,
	key string,
	version uint64,
	payload []byte,
) (bool, error) {
	vault.mu.Lock()
	defer vault.mu.Unlock()
	if vault.swapErr != nil {
		return false, vault.swapErr
	}
	record, exists := vault.records[key]
	if !exists || record.version != version {
		return false, nil
	}
	vault.records[key] = identitySecurityProcessorVaultTestRecord{
		payload: append([]byte(nil), payload...),
		version: record.version + 1,
	}
	return true, nil
}

func (vault *identitySecurityProcessorMemoryVault) Delete(
	_ context.Context,
	key string,
) error {
	vault.mu.Lock()
	defer vault.mu.Unlock()
	if vault.deleteErr != nil {
		return vault.deleteErr
	}
	delete(vault.records, key)
	return nil
}

func (vault *identitySecurityProcessorMemoryVault) recordCount() int {
	vault.mu.Lock()
	defer vault.mu.Unlock()
	return len(vault.records)
}

func (vault *identitySecurityProcessorMemoryVault) decodedRecord(
	t *testing.T,
	ref string,
) identitySecurityProcessorRecord {
	t.Helper()
	refToken := strings.TrimPrefix(ref, "isr_")
	vault.mu.Lock()
	payload := append([]byte(nil), vault.records[refToken].payload...)
	vault.mu.Unlock()
	var record identitySecurityProcessorRecord
	if err := json.Unmarshal(payload, &record); err != nil {
		t.Fatalf("decode processor record: %v", err)
	}
	clear(payload)
	return record
}

type identitySecurityProcessorRotatingKeys struct {
	mu   sync.Mutex
	ring IdentitySecurityProcessorKeyRing
	err  error
}

func (resolver *identitySecurityProcessorRotatingKeys) ResolveIdentitySecurityProcessorKeys(
	context.Context,
) (IdentitySecurityProcessorKeyRing, error) {
	resolver.mu.Lock()
	defer resolver.mu.Unlock()
	if resolver.err != nil {
		return IdentitySecurityProcessorKeyRing{}, resolver.err
	}
	ring := IdentitySecurityProcessorKeyRing{
		ActiveVersion: resolver.ring.ActiveVersion,
		Keys:          make(map[string][]byte, len(resolver.ring.Keys)),
	}
	for version, key := range resolver.ring.Keys {
		ring.Keys[version] = append([]byte(nil), key...)
	}
	return ring, nil
}

func (resolver *identitySecurityProcessorRotatingKeys) set(
	activeVersion string,
	keys map[string][]byte,
) {
	resolver.mu.Lock()
	defer resolver.mu.Unlock()
	resolver.ring = IdentitySecurityProcessorKeyRing{
		ActiveVersion: activeVersion,
		Keys:          make(map[string][]byte, len(keys)),
	}
	for version, key := range keys {
		resolver.ring.Keys[version] = append([]byte(nil), key...)
	}
}

type identitySecurityProcessorTestPasswordHasher struct{}

func (identitySecurityProcessorTestPasswordHasher) HashIdentitySecurityPassword(
	password []byte,
) ([]byte, error) {
	digest := sha256.Sum256(password)
	return []byte("$test$" + hex.EncodeToString(digest[:])), nil
}

func newIdentitySecurityProcessorVaultTestSubject(
	t *testing.T,
) (
	*VaultIdentitySecuritySecretProcessor,
	*identitySecurityProcessorMemoryVault,
	*identitySecurityProcessorRotatingKeys,
	time.Time,
) {
	t.Helper()
	vault := newIdentitySecurityProcessorMemoryVault()
	keys := &identitySecurityProcessorRotatingKeys{}
	keys.set("key-v1", map[string][]byte{
		"key-v1": bytes.Repeat([]byte{0x41}, 32),
	})
	now := time.Date(2026, time.July, 25, 9, 30, 0, 123456000, time.UTC)
	processor, err := NewVaultIdentitySecuritySecretProcessor(
		VaultIdentitySecuritySecretProcessorOptions{
			Vault:          vault,
			Keys:           keys,
			PasswordHasher: identitySecurityProcessorTestPasswordHasher{},
			Now:            func() time.Time { return now },
			Issuer:         "Ashr Test",
		},
	)
	if err != nil {
		t.Fatalf("new Vault processor: %v", err)
	}
	return processor, vault, keys, now
}

func TestArgon2IdentitySecurityPasswordHasherDoesNotExposePassword(t *testing.T) {
	password := []byte("correct horse battery staple")
	hasher := Argon2IdentitySecurityPasswordHasher{
		MemoryKiB:   32 * 1024,
		Iterations:  2,
		Parallelism: 1,
	}
	encoded, err := hasher.HashIdentitySecurityPassword(password)
	if err != nil {
		t.Fatalf("hash password: %v", err)
	}
	if !bytes.HasPrefix(encoded, []byte("$argon2id$")) {
		t.Fatalf("unexpected Argon2 encoding prefix")
	}
	if bytes.Contains(encoded, password) {
		t.Fatalf("Argon2 encoding exposed the raw password")
	}
	clear(encoded)
	clear(password)
}

func TestVaultIdentitySecurityProcessorPasswordIdempotencyAndCleanup(t *testing.T) {
	processor, vault, _, _ := newIdentitySecurityProcessorVaultTestSubject(t)
	request := IdentitySecuritySecretProcessRequest{
		AccountID:      identitySecurityProcessorVaultTestAccountID,
		Operation:      "password_enroll",
		IdempotencyKey: "password-enroll-0001",
		Password:       "correct horse battery staple",
	}
	first, err := processor.ProcessIdentitySecuritySecret(context.Background(), request)
	if err != nil {
		t.Fatalf("process password: %v", err)
	}
	second, err := processor.ProcessIdentitySecuritySecret(context.Background(), request)
	if err != nil {
		t.Fatalf("retry password: %v", err)
	}
	if first != second || vault.recordCount() != 1 {
		t.Fatalf("exact retry changed the processor projection")
	}
	conflict := request
	conflict.Password = "different secure password value"
	if _, err := processor.ProcessIdentitySecuritySecret(
		context.Background(),
		conflict,
	); !errors.Is(err, ErrIdentitySecurityProcessorRejected) {
		t.Fatalf("expected password conflict rejection, got %v", err)
	}
	record := vault.decodedRecord(t, first.SecretRef)
	if bytes.Contains(record.PasswordHash, []byte(request.Password)) {
		t.Fatalf("Vault record contains the raw password")
	}
	clearIdentitySecurityProcessorRecord(&record)

	cleanup := IdentitySecuritySecretCleanupRequest{
		AccountID:      request.AccountID,
		Operation:      request.Operation,
		IdempotencyKey: request.IdempotencyKey,
		CleanupToken:   first.CleanupToken,
	}
	if err := processor.CleanupIdentitySecuritySecret(
		context.Background(),
		cleanup,
	); err != nil {
		t.Fatalf("cleanup password: %v", err)
	}
	if vault.recordCount() != 0 {
		t.Fatalf("password cleanup left a partial record")
	}
	if err := processor.CleanupIdentitySecuritySecret(
		context.Background(),
		cleanup,
	); err != nil {
		t.Fatalf("idempotent cleanup: %v", err)
	}
	forged := cleanup
	forged.CleanupToken = forged.CleanupToken[:len(forged.CleanupToken)-1] + "A"
	if forged.CleanupToken == cleanup.CleanupToken {
		forged.CleanupToken = forged.CleanupToken[:len(forged.CleanupToken)-1] + "B"
	}
	if err := processor.CleanupIdentitySecuritySecret(
		context.Background(),
		forged,
	); !errors.Is(err, ErrIdentitySecurityProcessorRejected) {
		t.Fatalf("forged cleanup token was accepted: %v", err)
	}
}

func TestVaultIdentitySecurityProcessorMFALifecycleAndOneUseHandoffs(t *testing.T) {
	processor, vault, _, now := newIdentitySecurityProcessorVaultTestSubject(t)
	processRequest := IdentitySecuritySecretProcessRequest{
		AccountID:      identitySecurityProcessorVaultTestAccountID,
		Operation:      "mfa_enroll",
		IdempotencyKey: "mfa-enroll-0001",
	}
	processed, err := processor.ProcessIdentitySecuritySecret(
		context.Background(),
		processRequest,
	)
	if err != nil {
		t.Fatalf("process TOTP enrollment: %v", err)
	}
	provisioningRequest := IdentitySecuritySecretHandoffRequest{
		AccountID:      processRequest.AccountID,
		Operation:      processRequest.Operation,
		IdempotencyKey: processRequest.IdempotencyKey,
		HandoffID:      processed.HandoffID,
	}
	provisioning, err := processor.ConsumeIdentitySecuritySecretHandoff(
		context.Background(),
		provisioningRequest,
	)
	if err != nil {
		t.Fatalf("consume provisioning handoff: %v", err)
	}
	if _, err := processor.ConsumeIdentitySecuritySecretHandoff(
		context.Background(),
		provisioningRequest,
	); !errors.Is(err, ErrIdentitySecurityProcessorRejected) {
		t.Fatalf("provisioning handoff replay was not rejected: %v", err)
	}
	secret := identitySecurityProcessorTestTOTPSecret(t, provisioning.ProvisioningURI)
	code := identitySecurityTOTPCode(secret, now.Unix()/30)
	defer clear(secret)
	defer clear(code)

	wrongCode := append([]byte(nil), code...)
	if wrongCode[0] == '9' {
		wrongCode[0] = '0'
	} else {
		wrongCode[0]++
	}
	if _, err := processor.ConfirmIdentitySecuritySecret(
		context.Background(),
		IdentitySecuritySecretConfirmRequest{
			AccountID:      processRequest.AccountID,
			ChallengeID:    processed.ConfirmationChallengeID,
			Code:           string(wrongCode),
			IdempotencyKey: "mfa-confirm-0001",
		},
	); !errors.Is(err, ErrIdentitySecurityProcessorRejected) {
		t.Fatalf("invalid TOTP was not rejected: %v", err)
	}
	clear(wrongCode)

	confirmRequest := IdentitySecuritySecretConfirmRequest{
		AccountID:      processRequest.AccountID,
		ChallengeID:    processed.ConfirmationChallengeID,
		Code:           string(code),
		IdempotencyKey: "mfa-confirm-0001",
	}
	confirmed, err := processor.ConfirmIdentitySecuritySecret(
		context.Background(),
		confirmRequest,
	)
	if err != nil {
		t.Fatalf("confirm TOTP: %v", err)
	}
	retry, err := processor.ConfirmIdentitySecuritySecret(
		context.Background(),
		confirmRequest,
	)
	if err != nil || retry != confirmed {
		t.Fatalf("confirm retry changed projection: result=%+v err=%v", retry, err)
	}
	recoveryRequest := IdentitySecuritySecretHandoffRequest{
		AccountID:      processRequest.AccountID,
		Operation:      "mfa_confirm",
		IdempotencyKey: confirmRequest.IdempotencyKey,
		HandoffID:      confirmed.HandoffID,
	}
	recovery, err := processor.ConsumeIdentitySecuritySecretHandoff(
		context.Background(),
		recoveryRequest,
	)
	if err != nil {
		t.Fatalf("consume recovery handoff: %v", err)
	}
	if len(recovery.RecoveryCodes) != confirmed.RecoveryCodeCount ||
		!validIdentitySecurityRecoveryCodes(recovery.RecoveryCodes) {
		t.Fatalf("invalid recovery-code handoff")
	}
	if _, err := processor.ConsumeIdentitySecuritySecretHandoff(
		context.Background(),
		recoveryRequest,
	); !errors.Is(err, ErrIdentitySecurityProcessorRejected) {
		t.Fatalf("recovery handoff replay was not rejected: %v", err)
	}
	record := vault.decodedRecord(t, processed.SecretRef)
	if len(record.RecoveryCodes) != 0 || !record.RecoveryHandoffConsumed {
		t.Fatalf("one-use recovery material remained in the record")
	}
	clearIdentitySecurityProcessorRecord(&record)
	clearIdentitySecuritySecretHandoff(&provisioning)
	clearIdentitySecuritySecretHandoff(&recovery)
}

func TestVaultIdentitySecurityProcessorConfirmCleanupRollsBackRecoveryOnly(t *testing.T) {
	processor, vault, _, now := newIdentitySecurityProcessorVaultTestSubject(t)
	processRequest := IdentitySecuritySecretProcessRequest{
		AccountID:      identitySecurityProcessorVaultTestAccountID,
		Operation:      "mfa_enroll",
		IdempotencyKey: "mfa-enroll-cleanup-0001",
	}
	processed, err := processor.ProcessIdentitySecuritySecret(
		context.Background(),
		processRequest,
	)
	if err != nil {
		t.Fatalf("process TOTP enrollment: %v", err)
	}
	record := vault.decodedRecord(t, processed.SecretRef)
	code := identitySecurityTOTPCode(record.TOTPSecret, now.Unix()/30)
	clearIdentitySecurityProcessorRecord(&record)
	defer clear(code)
	confirmRequest := IdentitySecuritySecretConfirmRequest{
		AccountID:      processRequest.AccountID,
		ChallengeID:    processed.ConfirmationChallengeID,
		Code:           string(code),
		IdempotencyKey: "mfa-confirm-cleanup-0001",
	}
	confirmed, err := processor.ConfirmIdentitySecuritySecret(
		context.Background(),
		confirmRequest,
	)
	if err != nil {
		t.Fatalf("confirm TOTP: %v", err)
	}
	if err := processor.CleanupIdentitySecuritySecret(
		context.Background(),
		IdentitySecuritySecretCleanupRequest{
			AccountID:      processRequest.AccountID,
			Operation:      "mfa_confirm",
			IdempotencyKey: confirmRequest.IdempotencyKey,
			CleanupToken:   confirmed.CleanupToken,
		},
	); err != nil {
		t.Fatalf("cleanup confirmation: %v", err)
	}
	record = vault.decodedRecord(t, processed.SecretRef)
	if record.Confirmed || record.ConfirmIdempotencyKey != "" ||
		record.RecoveryBatchDigest != "" ||
		len(record.RecoveryCodeDigests) != 0 ||
		len(record.RecoveryCodes) != 0 ||
		len(record.TOTPSecret) != 20 {
		t.Fatalf("confirmation cleanup did not preserve only pending TOTP enrollment")
	}
	clearIdentitySecurityProcessorRecord(&record)
}

func TestVaultIdentitySecurityProcessorKeyRotation(t *testing.T) {
	processor, _, keys, now := newIdentitySecurityProcessorVaultTestSubject(t)
	processRequest := IdentitySecuritySecretProcessRequest{
		AccountID:      identitySecurityProcessorVaultTestAccountID,
		Operation:      "mfa_enroll",
		IdempotencyKey: "mfa-rotation-0001",
	}
	processed, err := processor.ProcessIdentitySecuritySecret(
		context.Background(),
		processRequest,
	)
	if err != nil || processed.KeyVersion != "key-v1" {
		t.Fatalf("process with key-v1: result=%+v err=%v", processed, err)
	}
	keys.set("key-v2", map[string][]byte{
		"key-v1": bytes.Repeat([]byte{0x41}, 32),
		"key-v2": bytes.Repeat([]byte{0x42}, 32),
	})
	secretRecord := processor.vault.(*identitySecurityProcessorMemoryVault).
		decodedRecord(t, processed.SecretRef)
	code := identitySecurityTOTPCode(secretRecord.TOTPSecret, now.Unix()/30)
	clearIdentitySecurityProcessorRecord(&secretRecord)
	defer clear(code)
	confirmed, err := processor.ConfirmIdentitySecuritySecret(
		context.Background(),
		IdentitySecuritySecretConfirmRequest{
			AccountID:      processRequest.AccountID,
			ChallengeID:    processed.ConfirmationChallengeID,
			Code:           string(code),
			IdempotencyKey: "mfa-rotation-confirm-0001",
		},
	)
	if err != nil || confirmed.KeyVersion != "key-v2" {
		t.Fatalf("confirm old record during rotation: result=%+v err=%v", confirmed, err)
	}
	passwordResult, err := processor.ProcessIdentitySecuritySecret(
		context.Background(),
		IdentitySecuritySecretProcessRequest{
			AccountID:      processRequest.AccountID,
			Operation:      "password_change",
			IdempotencyKey: "password-rotation-0001",
			Password:       "correct horse battery staple",
		},
	)
	if err != nil || passwordResult.KeyVersion != "key-v2" {
		t.Fatalf("new record did not use active key-v2: result=%+v err=%v", passwordResult, err)
	}
	keys.set("key-v2", map[string][]byte{
		"key-v2": bytes.Repeat([]byte{0x42}, 32),
	})
	if _, err := processor.ConfirmIdentitySecuritySecret(
		context.Background(),
		IdentitySecuritySecretConfirmRequest{
			AccountID:      processRequest.AccountID,
			ChallengeID:    processed.ConfirmationChallengeID,
			Code:           string(code),
			IdempotencyKey: "mfa-rotation-confirm-0001",
		},
	); !errors.Is(err, ErrIdentitySecurityProcessorRejected) {
		t.Fatalf("retired record key did not fail closed: %v", err)
	}
}

func TestVaultIdentitySecurityProcessorConcurrentIdempotencyAndHandoff(t *testing.T) {
	processor, vault, _, _ := newIdentitySecurityProcessorVaultTestSubject(t)
	request := IdentitySecuritySecretProcessRequest{
		AccountID:      identitySecurityProcessorVaultTestAccountID,
		Operation:      "mfa_enroll",
		IdempotencyKey: "mfa-concurrent-0001",
	}
	const workers = 32
	results := make(chan IdentitySecuritySecretProcessResult, workers)
	errs := make(chan error, workers)
	var wait sync.WaitGroup
	for index := 0; index < workers; index++ {
		wait.Add(1)
		go func() {
			defer wait.Done()
			result, err := processor.ProcessIdentitySecuritySecret(
				context.Background(),
				request,
			)
			results <- result
			errs <- err
		}()
	}
	wait.Wait()
	close(results)
	close(errs)
	for err := range errs {
		if err != nil {
			t.Fatalf("concurrent process: %v", err)
		}
	}
	var expected IdentitySecuritySecretProcessResult
	for result := range results {
		if expected.SecretRef == "" {
			expected = result
			continue
		}
		if result != expected {
			t.Fatalf("concurrent process projection mismatch")
		}
	}
	if vault.recordCount() != 1 {
		t.Fatalf("concurrent process created %d records", vault.recordCount())
	}

	handoffRequest := IdentitySecuritySecretHandoffRequest{
		AccountID:      request.AccountID,
		Operation:      request.Operation,
		IdempotencyKey: request.IdempotencyKey,
		HandoffID:      expected.HandoffID,
	}
	var successes atomic.Int32
	handoffErrs := make(chan error, workers)
	for index := 0; index < workers; index++ {
		wait.Add(1)
		go func() {
			defer wait.Done()
			_, err := processor.ConsumeIdentitySecuritySecretHandoff(
				context.Background(),
				handoffRequest,
			)
			if err == nil {
				successes.Add(1)
				return
			}
			if !errors.Is(err, ErrIdentitySecurityProcessorRejected) {
				handoffErrs <- err
			}
		}()
	}
	wait.Wait()
	close(handoffErrs)
	for err := range handoffErrs {
		t.Fatalf("concurrent handoff: %v", err)
	}
	if successes.Load() != 1 {
		t.Fatalf("expected one handoff winner, got %d", successes.Load())
	}
}

func TestVaultIdentitySecurityProcessorFailureAtomicityAndRedaction(t *testing.T) {
	processor, vault, keys, _ := newIdentitySecurityProcessorVaultTestSubject(t)
	secretMarker := "correct horse battery staple"
	request := IdentitySecuritySecretProcessRequest{
		AccountID:      identitySecurityProcessorVaultTestAccountID,
		Operation:      "password_enroll",
		IdempotencyKey: "password-failure-0001",
		Password:       secretMarker,
	}
	vault.createErr = errors.New("upstream included " + secretMarker)
	if _, err := processor.ProcessIdentitySecuritySecret(
		context.Background(),
		request,
	); !errors.Is(err, ErrIdentitySecurityProcessorUnavailable) ||
		strings.Contains(err.Error(), secretMarker) {
		t.Fatalf("create failure was not safely redacted: %v", err)
	}
	if vault.recordCount() != 0 {
		t.Fatalf("create failure left a partial record")
	}
	vault.createErr = nil
	processed, err := processor.ProcessIdentitySecuritySecret(
		context.Background(),
		request,
	)
	if err != nil {
		t.Fatalf("process after create recovery: %v", err)
	}
	vault.deleteErr = errors.New("upstream included " + secretMarker)
	if err := processor.CleanupIdentitySecuritySecret(
		context.Background(),
		IdentitySecuritySecretCleanupRequest{
			AccountID:      request.AccountID,
			Operation:      request.Operation,
			IdempotencyKey: request.IdempotencyKey,
			CleanupToken:   processed.CleanupToken,
		},
	); !errors.Is(err, ErrIdentitySecurityProcessorUnavailable) ||
		strings.Contains(err.Error(), secretMarker) {
		t.Fatalf("delete failure was not safely redacted: %v", err)
	}
	if vault.recordCount() != 1 {
		t.Fatalf("delete failure removed the record")
	}
	vault.deleteErr = nil
	keys.err = errors.New("key resolver included " + secretMarker)
	if err := processor.Ready(context.Background()); !errors.Is(
		err,
		ErrIdentitySecurityProcessorUnavailable,
	) || strings.Contains(err.Error(), secretMarker) {
		t.Fatalf("key resolver failure was not safely redacted: %v", err)
	}
}

func identitySecurityProcessorTestTOTPSecret(
	t *testing.T,
	provisioningURI string,
) []byte {
	t.Helper()
	parsed, err := url.Parse(provisioningURI)
	if err != nil {
		t.Fatalf("parse provisioning URI: %v", err)
	}
	secret, err := base32.StdEncoding.WithPadding(base32.NoPadding).
		DecodeString(parsed.Query().Get("secret"))
	if err != nil {
		t.Fatalf("decode provisioning secret: %v", err)
	}
	return secret
}

var (
	_ IdentitySecurityProcessorVault       = (*identitySecurityProcessorMemoryVault)(nil)
	_ IdentitySecurityProcessorKeyResolver = (*identitySecurityProcessorRotatingKeys)(nil)
)
