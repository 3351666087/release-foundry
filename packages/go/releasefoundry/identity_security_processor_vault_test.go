package releasefoundry

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base32"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
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
			Issuer:         "ReleaseFoundry Test",
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

func TestVaultIdentitySecurityProcessorRecoveryMutationLifecycle(t *testing.T) {
	processor, vault, _, _ := newIdentitySecurityProcessorVaultTestSubject(t)
	processed, recoveryCodes := identitySecurityProcessorTestConfirmedMFA(
		t,
		processor,
		vault,
		"mutation-lifecycle",
	)
	record := vault.decodedRecord(t, processed.SecretRef)
	initialBatch := record.RecoveryBatchDigest
	initialCount := len(record.RecoveryCodeDigests)
	initialTOTPSecret := append([]byte(nil), record.TOTPSecret...)
	clearIdentitySecurityProcessorRecord(&record)
	defer clear(initialTOTPSecret)

	consumeRequest := IdentitySecuritySecretMutationPrepareRequest{
		AccountID:                   identitySecurityProcessorVaultTestAccountID,
		Operation:                   "mfa_recovery_consume",
		IdempotencyKey:              "recovery-consume-0001",
		SecretRef:                   processed.SecretRef,
		SecretDigest:                processed.SecretDigest,
		ExpectedRecoveryBatchDigest: initialBatch,
		ExpectedRecoveryCodeCount:   initialCount,
		RecoveryCode:                recoveryCodes[0],
	}
	consumed, err := processor.PrepareIdentitySecuritySecretMutation(
		context.Background(),
		consumeRequest,
	)
	if err != nil {
		t.Fatalf("prepare recovery consume: %v", err)
	}
	if consumed.RecoveryCodeCount != initialCount-1 ||
		consumed.ExpectedRecoveryBatchDigest != initialBatch ||
		consumed.ExpectedRecoveryCodeCount != initialCount ||
		consumed.RecoveryBatchDigest == initialBatch ||
		consumed.HandoffID != "" {
		t.Fatalf("invalid recovery consume projection: %+v", consumed)
	}
	replayed, err := processor.PrepareIdentitySecuritySecretMutation(
		context.Background(),
		consumeRequest,
	)
	if err != nil || replayed != consumed {
		t.Fatalf("exact consume retry changed projection: result=%+v err=%v", replayed, err)
	}
	conflict := consumeRequest
	conflict.RecoveryCode = recoveryCodes[1]
	if _, err := processor.PrepareIdentitySecuritySecretMutation(
		context.Background(),
		conflict,
	); !errors.Is(err, ErrIdentitySecurityProcessorRejected) {
		t.Fatalf("same idempotency with a different code was accepted: %v", err)
	}
	wrongAccount := consumeRequest
	wrongAccount.AccountID = "55555555-5555-4555-8555-555555555555"
	if _, err := processor.PrepareIdentitySecuritySecretMutation(
		context.Background(),
		wrongAccount,
	); !errors.Is(err, ErrIdentitySecurityProcessorRejected) {
		t.Fatalf("wrong-account recovery consume was accepted: %v", err)
	}
	if _, err := processor.PrepareIdentitySecuritySecretMutation(
		context.Background(),
		IdentitySecuritySecretMutationPrepareRequest{
			AccountID:                   consumeRequest.AccountID,
			Operation:                   "mfa_recovery_rotate",
			IdempotencyKey:              "recovery-rotate-blocked-0001",
			SecretRef:                   consumeRequest.SecretRef,
			SecretDigest:                consumeRequest.SecretDigest,
			ExpectedRecoveryBatchDigest: consumed.RecoveryBatchDigest,
			ExpectedRecoveryCodeCount:   consumed.RecoveryCodeCount,
		},
	); !errors.Is(err, ErrIdentitySecurityProcessorRejected) {
		t.Fatalf("pending consume did not block rotation: %v", err)
	}
	if err := processor.CleanupIdentitySecuritySecret(
		context.Background(),
		IdentitySecuritySecretCleanupRequest{
			AccountID:      consumeRequest.AccountID,
			Operation:      consumeRequest.Operation,
			IdempotencyKey: consumeRequest.IdempotencyKey,
			CleanupToken:   consumed.CleanupToken,
		},
	); err != nil {
		t.Fatalf("rollback recovery consume: %v", err)
	}
	record = vault.decodedRecord(t, processed.SecretRef)
	if record.PendingOperation != "" ||
		record.RecoveryBatchDigest != initialBatch ||
		len(record.RecoveryCodeDigests) != initialCount ||
		!record.RecoveryHandoffConsumed ||
		!bytes.Equal(record.TOTPSecret, initialTOTPSecret) {
		t.Fatalf("recovery consume rollback did not restore the exact prior state")
	}
	clearIdentitySecurityProcessorRecord(&record)

	consumed, err = processor.PrepareIdentitySecuritySecretMutation(
		context.Background(),
		consumeRequest,
	)
	if err != nil {
		t.Fatalf("prepare recovery consume after rollback: %v", err)
	}
	if err := processor.FinalizeIdentitySecuritySecretMutation(
		context.Background(),
		IdentitySecuritySecretMutationFinalizeRequest{
			AccountID:      consumeRequest.AccountID,
			Operation:      consumeRequest.Operation,
			IdempotencyKey: consumeRequest.IdempotencyKey,
			FinalizeToken:  consumed.FinalizeToken,
		},
	); err != nil {
		t.Fatalf("finalize recovery consume: %v", err)
	}
	if err := processor.FinalizeIdentitySecuritySecretMutation(
		context.Background(),
		IdentitySecuritySecretMutationFinalizeRequest{
			AccountID:      consumeRequest.AccountID,
			Operation:      consumeRequest.Operation,
			IdempotencyKey: consumeRequest.IdempotencyKey,
			FinalizeToken:  consumed.FinalizeToken,
		},
	); err != nil {
		t.Fatalf("replay recovery consume finalize: %v", err)
	}
	usedCode := consumeRequest
	usedCode.IdempotencyKey = "recovery-consume-used-0002"
	usedCode.ExpectedRecoveryBatchDigest = consumed.RecoveryBatchDigest
	usedCode.ExpectedRecoveryCodeCount = consumed.RecoveryCodeCount
	if _, err := processor.PrepareIdentitySecuritySecretMutation(
		context.Background(),
		usedCode,
	); !errors.Is(err, ErrIdentitySecurityProcessorRejected) {
		t.Fatalf("consumed recovery code was accepted again: %v", err)
	}

	rotateRequest := IdentitySecuritySecretMutationPrepareRequest{
		AccountID:                   consumeRequest.AccountID,
		Operation:                   "mfa_recovery_rotate",
		IdempotencyKey:              "recovery-rotate-0001",
		SecretRef:                   consumeRequest.SecretRef,
		SecretDigest:                consumeRequest.SecretDigest,
		ExpectedRecoveryBatchDigest: consumed.RecoveryBatchDigest,
		ExpectedRecoveryCodeCount:   consumed.RecoveryCodeCount,
	}
	rotated, err := processor.PrepareIdentitySecuritySecretMutation(
		context.Background(),
		rotateRequest,
	)
	if err != nil {
		t.Fatalf("prepare recovery rotation: %v", err)
	}
	if rotated.HandoffID == "" ||
		rotated.RecoveryCodeCount < 6 ||
		rotated.RecoveryBatchDigest == consumed.RecoveryBatchDigest {
		t.Fatalf("invalid recovery rotation projection: %+v", rotated)
	}
	if replayed, retryErr := processor.PrepareIdentitySecuritySecretMutation(
		context.Background(),
		rotateRequest,
	); retryErr != nil || replayed != rotated {
		t.Fatalf("exact rotation retry changed projection: result=%+v err=%v", replayed, retryErr)
	}
	handoffRequest := IdentitySecuritySecretHandoffRequest{
		AccountID:      rotateRequest.AccountID,
		Operation:      rotateRequest.Operation,
		IdempotencyKey: rotateRequest.IdempotencyKey,
		HandoffID:      rotated.HandoffID,
	}
	if _, err := processor.ConsumeIdentitySecuritySecretHandoff(
		context.Background(),
		handoffRequest,
	); !errors.Is(err, ErrIdentitySecurityProcessorRejected) {
		t.Fatalf("rotated recovery codes were handed off before finalize: %v", err)
	}
	if err := processor.FinalizeIdentitySecuritySecretMutation(
		context.Background(),
		IdentitySecuritySecretMutationFinalizeRequest{
			AccountID:      rotateRequest.AccountID,
			Operation:      rotateRequest.Operation,
			IdempotencyKey: rotateRequest.IdempotencyKey,
			FinalizeToken:  rotated.FinalizeToken,
		},
	); err != nil {
		t.Fatalf("finalize recovery rotation: %v", err)
	}
	rotatedCodes, err := processor.ConsumeIdentitySecuritySecretHandoff(
		context.Background(),
		handoffRequest,
	)
	if err != nil || len(rotatedCodes.RecoveryCodes) != rotated.RecoveryCodeCount ||
		!validIdentitySecurityRecoveryCodes(rotatedCodes.RecoveryCodes) {
		t.Fatalf("consume rotated recovery codes: handoff=%+v err=%v", rotatedCodes, err)
	}
	if _, err := processor.ConsumeIdentitySecuritySecretHandoff(
		context.Background(),
		handoffRequest,
	); !errors.Is(err, ErrIdentitySecurityProcessorRejected) {
		t.Fatalf("rotated recovery handoff replay was accepted: %v", err)
	}
	record = vault.decodedRecord(t, processed.SecretRef)
	if record.PendingOperation != "" ||
		!record.RecoveryHandoffConsumed ||
		len(record.RecoveryCodes) != 0 ||
		record.RecoveryBatchDigest != rotated.RecoveryBatchDigest ||
		len(record.RecoveryCodeDigests) != rotated.RecoveryCodeCount {
		t.Fatalf("rotation handoff did not leave only active digests")
	}
	clearIdentitySecurityProcessorRecord(&record)

	disableRequest := IdentitySecuritySecretMutationPrepareRequest{
		AccountID:                   rotateRequest.AccountID,
		Operation:                   "mfa_disable",
		IdempotencyKey:              "mfa-disable-0001",
		SecretRef:                   rotateRequest.SecretRef,
		SecretDigest:                rotateRequest.SecretDigest,
		ExpectedRecoveryBatchDigest: rotated.RecoveryBatchDigest,
		ExpectedRecoveryCodeCount:   rotated.RecoveryCodeCount,
	}
	disabled, err := processor.PrepareIdentitySecuritySecretMutation(
		context.Background(),
		disableRequest,
	)
	if err != nil {
		t.Fatalf("prepare MFA disable: %v", err)
	}
	record = vault.decodedRecord(t, processed.SecretRef)
	if record.Confirmed || len(record.TOTPSecret) != 0 ||
		record.RecoveryBatchDigest != "" ||
		len(record.RecoveryCodeDigests) != 0 ||
		record.PendingOperation != "mfa_disable" ||
		!bytes.Equal(record.PreviousTOTPSecret, initialTOTPSecret) {
		t.Fatalf("MFA disable prepare left active secret material available")
	}
	clearIdentitySecurityProcessorRecord(&record)
	if err := processor.CleanupIdentitySecuritySecret(
		context.Background(),
		IdentitySecuritySecretCleanupRequest{
			AccountID:      disableRequest.AccountID,
			Operation:      disableRequest.Operation,
			IdempotencyKey: disableRequest.IdempotencyKey,
			CleanupToken:   disabled.CleanupToken,
		},
	); err != nil {
		t.Fatalf("rollback MFA disable: %v", err)
	}
	record = vault.decodedRecord(t, processed.SecretRef)
	if !record.Confirmed ||
		!bytes.Equal(record.TOTPSecret, initialTOTPSecret) ||
		record.RecoveryBatchDigest != rotated.RecoveryBatchDigest ||
		len(record.RecoveryCodeDigests) != rotated.RecoveryCodeCount ||
		record.PendingOperation != "" {
		t.Fatalf("MFA disable rollback did not restore active state")
	}
	clearIdentitySecurityProcessorRecord(&record)
	disabled, err = processor.PrepareIdentitySecuritySecretMutation(
		context.Background(),
		disableRequest,
	)
	if err != nil {
		t.Fatalf("prepare MFA disable after rollback: %v", err)
	}
	if err := processor.FinalizeIdentitySecuritySecretMutation(
		context.Background(),
		IdentitySecuritySecretMutationFinalizeRequest{
			AccountID:      disableRequest.AccountID,
			Operation:      disableRequest.Operation,
			IdempotencyKey: disableRequest.IdempotencyKey,
			FinalizeToken:  disabled.FinalizeToken,
		},
	); err != nil {
		t.Fatalf("finalize MFA disable: %v", err)
	}
	if vault.recordCount() != 0 {
		t.Fatalf("finalized MFA disable retained the Vault record")
	}
	if err := processor.FinalizeIdentitySecuritySecretMutation(
		context.Background(),
		IdentitySecuritySecretMutationFinalizeRequest{
			AccountID:      disableRequest.AccountID,
			Operation:      disableRequest.Operation,
			IdempotencyKey: disableRequest.IdempotencyKey,
			FinalizeToken:  disabled.FinalizeToken,
		},
	); err != nil {
		t.Fatalf("MFA disable finalize replay failed: %v", err)
	}
	clearIdentitySecuritySecretHandoff(&rotatedCodes)
}

func TestVaultIdentitySecurityProcessorRecoveryCodeConcurrentSingleWinner(t *testing.T) {
	processor, vault, _, _ := newIdentitySecurityProcessorVaultTestSubject(t)
	processed, recoveryCodes := identitySecurityProcessorTestConfirmedMFA(
		t,
		processor,
		vault,
		"concurrent-recovery",
	)
	record := vault.decodedRecord(t, processed.SecretRef)
	expectedBatch := record.RecoveryBatchDigest
	expectedCount := len(record.RecoveryCodeDigests)
	clearIdentitySecurityProcessorRecord(&record)

	const workers = 24
	type outcome struct {
		request IdentitySecuritySecretMutationPrepareRequest
		result  IdentitySecuritySecretMutationPrepareResult
		err     error
	}
	outcomes := make(chan outcome, workers)
	var wait sync.WaitGroup
	for index := 0; index < workers; index++ {
		wait.Add(1)
		go func(worker int) {
			defer wait.Done()
			request := IdentitySecuritySecretMutationPrepareRequest{
				AccountID:                   identitySecurityProcessorVaultTestAccountID,
				Operation:                   "mfa_recovery_consume",
				IdempotencyKey:              fmt.Sprintf("concurrent-recovery-%04d", worker),
				SecretRef:                   processed.SecretRef,
				SecretDigest:                processed.SecretDigest,
				ExpectedRecoveryBatchDigest: expectedBatch,
				ExpectedRecoveryCodeCount:   expectedCount,
				RecoveryCode:                recoveryCodes[0],
			}
			result, err := processor.PrepareIdentitySecuritySecretMutation(
				context.Background(),
				request,
			)
			outcomes <- outcome{request: request, result: result, err: err}
		}(index)
	}
	wait.Wait()
	close(outcomes)

	var winner *outcome
	for current := range outcomes {
		if current.err == nil {
			if winner != nil {
				t.Fatalf("same recovery code produced multiple concurrent winners")
			}
			copy := current
			winner = &copy
			continue
		}
		if !errors.Is(current.err, ErrIdentitySecurityProcessorRejected) {
			t.Fatalf("unexpected concurrent recovery error: %v", current.err)
		}
	}
	if winner == nil {
		t.Fatal("same recovery code produced no concurrent winner")
	}
	if err := processor.FinalizeIdentitySecuritySecretMutation(
		context.Background(),
		IdentitySecuritySecretMutationFinalizeRequest{
			AccountID:      winner.request.AccountID,
			Operation:      winner.request.Operation,
			IdempotencyKey: winner.request.IdempotencyKey,
			FinalizeToken:  winner.result.FinalizeToken,
		},
	); err != nil {
		t.Fatalf("finalize concurrent recovery winner: %v", err)
	}
	record = vault.decodedRecord(t, processed.SecretRef)
	if len(record.RecoveryCodeDigests) != expectedCount-1 ||
		record.RecoveryBatchDigest != winner.result.RecoveryBatchDigest {
		t.Fatalf("concurrent recovery winner did not commit exactly one digest removal")
	}
	clearIdentitySecurityProcessorRecord(&record)
}

func TestVaultIdentitySecurityProcessorDisableDeleteRetryIsFailClosed(t *testing.T) {
	processor, vault, keys, _ := newIdentitySecurityProcessorVaultTestSubject(t)
	processed, _ := identitySecurityProcessorTestConfirmedMFA(
		t,
		processor,
		vault,
		"disable-delete-retry",
	)
	record := vault.decodedRecord(t, processed.SecretRef)
	request := IdentitySecuritySecretMutationPrepareRequest{
		AccountID:                   identitySecurityProcessorVaultTestAccountID,
		Operation:                   "mfa_disable",
		IdempotencyKey:              "disable-delete-retry-0001",
		SecretRef:                   processed.SecretRef,
		SecretDigest:                processed.SecretDigest,
		ExpectedRecoveryBatchDigest: record.RecoveryBatchDigest,
		ExpectedRecoveryCodeCount:   len(record.RecoveryCodeDigests),
	}
	clearIdentitySecurityProcessorRecord(&record)
	keys.set("key-v2", map[string][]byte{
		"key-v1": bytes.Repeat([]byte{0x41}, 32),
		"key-v2": bytes.Repeat([]byte{0x42}, 32),
	})
	prepared, err := processor.PrepareIdentitySecuritySecretMutation(
		context.Background(),
		request,
	)
	if err != nil || prepared.KeyVersion != "key-v2" {
		t.Fatalf("prepare disable under rotated key: result=%+v err=%v", prepared, err)
	}
	const secretMarker = "delete-upstream-secret-must-not-leak"
	vault.deleteErr = errors.New(secretMarker)
	finalizeRequest := IdentitySecuritySecretMutationFinalizeRequest{
		AccountID:      request.AccountID,
		Operation:      request.Operation,
		IdempotencyKey: request.IdempotencyKey,
		FinalizeToken:  prepared.FinalizeToken,
	}
	if err := processor.FinalizeIdentitySecuritySecretMutation(
		context.Background(),
		finalizeRequest,
	); !errors.Is(err, ErrIdentitySecurityProcessorUnavailable) ||
		strings.Contains(err.Error(), secretMarker) {
		t.Fatalf("disable delete failure was not safely redacted: %v", err)
	}
	record = vault.decodedRecord(t, processed.SecretRef)
	if !record.PendingFinalized ||
		record.PendingOperation != "mfa_disable" ||
		len(record.PreviousTOTPSecret) != 0 ||
		len(record.PreviousRecoveryDigests) != 0 {
		t.Fatalf("delete failure did not leave a fail-closed finalized tombstone")
	}
	clearIdentitySecurityProcessorRecord(&record)
	if err := processor.CleanupIdentitySecuritySecret(
		context.Background(),
		IdentitySecuritySecretCleanupRequest{
			AccountID:      request.AccountID,
			Operation:      request.Operation,
			IdempotencyKey: request.IdempotencyKey,
			CleanupToken:   prepared.CleanupToken,
		},
	); !errors.Is(err, ErrIdentitySecurityProcessorRejected) {
		t.Fatalf("finalized disable tombstone was rolled back: %v", err)
	}
	vault.deleteErr = nil
	if err := processor.FinalizeIdentitySecuritySecretMutation(
		context.Background(),
		finalizeRequest,
	); err != nil {
		t.Fatalf("retry disable tombstone delete: %v", err)
	}
	if vault.recordCount() != 0 {
		t.Fatalf("disable finalize retry retained the tombstone")
	}
}

func identitySecurityProcessorTestConfirmedMFA(
	t *testing.T,
	processor *VaultIdentitySecuritySecretProcessor,
	vault *identitySecurityProcessorMemoryVault,
	suffix string,
) (IdentitySecuritySecretProcessResult, []string) {
	t.Helper()
	processRequest := IdentitySecuritySecretProcessRequest{
		AccountID:      identitySecurityProcessorVaultTestAccountID,
		Operation:      "mfa_enroll",
		IdempotencyKey: "mfa-enroll-" + suffix,
	}
	processed, err := processor.ProcessIdentitySecuritySecret(
		context.Background(),
		processRequest,
	)
	if err != nil {
		t.Fatalf("process confirmed MFA fixture: %v", err)
	}
	record := vault.decodedRecord(t, processed.SecretRef)
	code := identitySecurityTOTPCode(record.TOTPSecret, processor.now().Unix()/30)
	clearIdentitySecurityProcessorRecord(&record)
	defer clear(code)
	confirmRequest := IdentitySecuritySecretConfirmRequest{
		AccountID:      processRequest.AccountID,
		ChallengeID:    processed.ConfirmationChallengeID,
		Code:           string(code),
		IdempotencyKey: "mfa-confirm-" + suffix,
	}
	confirmed, err := processor.ConfirmIdentitySecuritySecret(
		context.Background(),
		confirmRequest,
	)
	if err != nil {
		t.Fatalf("confirm MFA fixture: %v", err)
	}
	handoff, err := processor.ConsumeIdentitySecuritySecretHandoff(
		context.Background(),
		IdentitySecuritySecretHandoffRequest{
			AccountID:      processRequest.AccountID,
			Operation:      "mfa_confirm",
			IdempotencyKey: confirmRequest.IdempotencyKey,
			HandoffID:      confirmed.HandoffID,
		},
	)
	if err != nil || !validIdentitySecurityRecoveryCodes(handoff.RecoveryCodes) {
		t.Fatalf("consume MFA fixture recovery codes: handoff=%+v err=%v", handoff, err)
	}
	recoveryCodes := append([]string(nil), handoff.RecoveryCodes...)
	clearIdentitySecuritySecretHandoff(&handoff)
	return processed, recoveryCodes
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
