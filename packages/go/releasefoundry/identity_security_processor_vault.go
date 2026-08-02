package releasefoundry

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha1"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base32"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/url"
	"sort"
	"strings"
	"time"

	"golang.org/x/crypto/argon2"
)

const (
	identitySecurityProcessorRecordSchema = "releasefoundry.identity_security_processor_record.v1"
	identitySecurityProcessorDigestSchema = "releasefoundry.identity_security_processor_digest.v1"
	identitySecurityProcessorRefTokenSize = 43
	identitySecurityProcessorTagSize      = 22
)

var ErrIdentitySecurityProcessorVaultRecordNotFound = errors.New(
	"identity security processor vault record not found",
)

// IdentitySecurityProcessorVault keeps processor records inside an external
// Vault or Secret Manager. Create and CompareAndSwap must be atomic so multiple
// processor replicas cannot expose a handoff more than once.
type IdentitySecurityProcessorVault interface {
	Ready(context.Context) error
	Read(
		context.Context,
		string,
	) (payload []byte, version uint64, err error)
	Create(context.Context, string, []byte) (bool, error)
	CompareAndSwap(
		context.Context,
		string,
		uint64,
		[]byte,
	) (bool, error)
	Delete(context.Context, string) error
}

type IdentitySecurityProcessorKeyRing struct {
	ActiveVersion string
	Keys          map[string][]byte
}

// IdentitySecurityProcessorKeyResolver resolves a reference-backed key ring.
// Implementations must keep key material outside environment variables,
// frontend configuration, repository files, logs, and browser storage. Each
// resolution must return caller-owned key buffers because the processor clears
// them after use.
type IdentitySecurityProcessorKeyResolver interface {
	ResolveIdentitySecurityProcessorKeys(
		context.Context,
	) (IdentitySecurityProcessorKeyRing, error)
}

type IdentitySecurityPasswordHasher interface {
	HashIdentitySecurityPassword([]byte) ([]byte, error)
}

type Argon2IdentitySecurityPasswordHasher struct {
	MemoryKiB   uint32
	Iterations  uint32
	Parallelism uint8
	SaltBytes   int
	OutputBytes uint32
	Random      io.Reader
}

func (hasher Argon2IdentitySecurityPasswordHasher) HashIdentitySecurityPassword(
	password []byte,
) ([]byte, error) {
	if len(password) < 12 || len(password) > 1024 {
		return nil, ErrIdentitySecurityProcessorRejected
	}
	if hasher.MemoryKiB == 0 {
		hasher.MemoryKiB = 64 * 1024
	}
	if hasher.Iterations == 0 {
		hasher.Iterations = 3
	}
	if hasher.Parallelism == 0 {
		hasher.Parallelism = 2
	}
	if hasher.SaltBytes == 0 {
		hasher.SaltBytes = 16
	}
	if hasher.OutputBytes == 0 {
		hasher.OutputBytes = 32
	}
	if hasher.Random == nil {
		hasher.Random = rand.Reader
	}
	if hasher.MemoryKiB < 32*1024 || hasher.MemoryKiB > 1024*1024 ||
		hasher.Iterations < 2 || hasher.Iterations > 10 ||
		hasher.Parallelism < 1 || hasher.Parallelism > 16 ||
		hasher.SaltBytes < 16 || hasher.SaltBytes > 64 ||
		hasher.OutputBytes < 32 || hasher.OutputBytes > 64 {
		return nil, ErrIdentitySecurityProcessorRejected
	}
	salt := make([]byte, hasher.SaltBytes)
	if _, err := io.ReadFull(hasher.Random, salt); err != nil {
		clear(salt)
		return nil, ErrIdentitySecurityProcessorUnavailable
	}
	digest := argon2.IDKey(
		password,
		salt,
		hasher.Iterations,
		hasher.MemoryKiB,
		hasher.Parallelism,
		hasher.OutputBytes,
	)
	encoded := []byte(fmt.Sprintf(
		"$argon2id$v=%d$m=%d,t=%d,p=%d$%s$%s",
		argon2.Version,
		hasher.MemoryKiB,
		hasher.Iterations,
		hasher.Parallelism,
		base64.RawStdEncoding.EncodeToString(salt),
		base64.RawStdEncoding.EncodeToString(digest),
	))
	clear(salt)
	clear(digest)
	return encoded, nil
}

type VaultIdentitySecuritySecretProcessorOptions struct {
	Vault             IdentitySecurityProcessorVault
	Keys              IdentitySecurityProcessorKeyResolver
	PasswordHasher    IdentitySecurityPasswordHasher
	Random            io.Reader
	Now               func() time.Time
	Issuer            string
	RecoveryCodeCount int
}

// VaultIdentitySecuritySecretProcessor is the trusted server-side processor.
// It stores only encrypted-at-rest Vault records, uses CAS for idempotency and
// one-use handoff claims, and returns only opaque references/keyed digests to
// the API runtime.
type VaultIdentitySecuritySecretProcessor struct {
	vault             IdentitySecurityProcessorVault
	keys              IdentitySecurityProcessorKeyResolver
	passwordHasher    IdentitySecurityPasswordHasher
	random            io.Reader
	now               func() time.Time
	issuer            string
	recoveryCodeCount int
}

type identitySecurityProcessorRecord struct {
	SchemaVersion            string    `json:"schema_version"`
	AccountID                string    `json:"account_id"`
	Operation                string    `json:"operation"`
	IdempotencyKey           string    `json:"idempotency_key"`
	KeyVersion               string    `json:"key_version"`
	RequestDigest            string    `json:"request_digest"`
	SecretRef                string    `json:"secret_ref"`
	SecretDigest             string    `json:"secret_digest"`
	PasswordHash             []byte    `json:"password_hash,omitempty"`
	TOTPSecret               []byte    `json:"totp_secret,omitempty"`
	ProvisioningConsumed     bool      `json:"provisioning_consumed,omitempty"`
	Confirmed                bool      `json:"confirmed,omitempty"`
	ConfirmIdempotencyKey    string    `json:"confirm_idempotency_key,omitempty"`
	RecoveryKeyVersion       string    `json:"recovery_key_version,omitempty"`
	RecoveryBatchDigest      string    `json:"recovery_batch_digest,omitempty"`
	RecoveryCodeDigests      []string  `json:"recovery_code_digests,omitempty"`
	RecoveryCodes            [][]byte  `json:"recovery_codes,omitempty"`
	RecoveryHandoffConsumed  bool      `json:"recovery_handoff_consumed,omitempty"`
	PendingOperation         string    `json:"pending_operation,omitempty"`
	PendingIdempotencyKey    string    `json:"pending_idempotency_key,omitempty"`
	PendingRequestDigest     string    `json:"pending_request_digest,omitempty"`
	PendingKeyVersion        string    `json:"pending_key_version,omitempty"`
	PendingExpectedBatch     string    `json:"pending_expected_batch,omitempty"`
	PendingExpectedCount     int       `json:"pending_expected_count,omitempty"`
	PendingFinalized         bool      `json:"pending_finalized,omitempty"`
	PreviousConfirmed        bool      `json:"previous_confirmed,omitempty"`
	PreviousTOTPSecret       []byte    `json:"previous_totp_secret,omitempty"`
	PreviousRecoveryVersion  string    `json:"previous_recovery_version,omitempty"`
	PreviousRecoveryBatch    string    `json:"previous_recovery_batch,omitempty"`
	PreviousRecoveryDigests  []string  `json:"previous_recovery_digests,omitempty"`
	PreviousRecoveryCodes    [][]byte  `json:"previous_recovery_codes,omitempty"`
	PreviousHandoffConsumed  bool      `json:"previous_handoff_consumed,omitempty"`
	CreatedAt                time.Time `json:"created_at"`
	LastSecurityTransitionAt time.Time `json:"last_security_transition_at"`
}

func NewVaultIdentitySecuritySecretProcessor(
	options VaultIdentitySecuritySecretProcessorOptions,
) (*VaultIdentitySecuritySecretProcessor, error) {
	if options.Vault == nil || options.Keys == nil {
		return nil, errors.New("identity security processor Vault and key resolver are required")
	}
	if options.PasswordHasher == nil {
		options.PasswordHasher = Argon2IdentitySecurityPasswordHasher{}
	}
	if options.Random == nil {
		options.Random = rand.Reader
	}
	if options.Now == nil {
		options.Now = time.Now
	}
	options.Issuer = strings.TrimSpace(options.Issuer)
	if options.Issuer == "" {
		options.Issuer = "ReleaseFoundry"
	}
	if len(options.Issuer) > 64 ||
		strings.ContainsAny(options.Issuer, "\x00\r\n\t:/?#[]@") {
		return nil, errors.New("identity security processor issuer is invalid")
	}
	if options.RecoveryCodeCount == 0 {
		options.RecoveryCodeCount = 10
	}
	if options.RecoveryCodeCount < 6 || options.RecoveryCodeCount > 20 {
		return nil, errors.New("identity security recovery code count must be between 6 and 20")
	}
	return &VaultIdentitySecuritySecretProcessor{
		vault:             options.Vault,
		keys:              options.Keys,
		passwordHasher:    options.PasswordHasher,
		random:            options.Random,
		now:               options.Now,
		issuer:            options.Issuer,
		recoveryCodeCount: options.RecoveryCodeCount,
	}, nil
}

func (processor *VaultIdentitySecuritySecretProcessor) Ready(
	ctx context.Context,
) error {
	if processor == nil || processor.vault == nil || processor.keys == nil ||
		ctx == nil {
		return ErrIdentitySecurityProcessorUnavailable
	}
	if err := processor.vault.Ready(ctx); err != nil {
		return ErrIdentitySecurityProcessorUnavailable
	}
	ring, err := processor.resolveKeyRing(ctx)
	if err != nil {
		return err
	}
	clearIdentitySecurityProcessorKeyRing(&ring)
	return nil
}

func (processor *VaultIdentitySecuritySecretProcessor) ProcessIdentitySecuritySecret(
	ctx context.Context,
	request IdentitySecuritySecretProcessRequest,
) (IdentitySecuritySecretProcessResult, error) {
	request.AccountID = strings.TrimSpace(request.AccountID)
	request.Operation = strings.TrimSpace(request.Operation)
	request.IdempotencyKey = strings.TrimSpace(request.IdempotencyKey)
	if processor == nil || processor.vault == nil || processor.keys == nil ||
		processor.passwordHasher == nil || processor.random == nil ||
		processor.now == nil || ctx == nil ||
		!validIdentitySecuritySecretProcessRequest(request) {
		request.Password = ""
		return IdentitySecuritySecretProcessResult{}, ErrIdentitySecurityProcessorRejected
	}
	password := []byte(request.Password)
	request.Password = ""
	defer clear(password)

	ring, err := processor.resolveKeyRing(ctx)
	if err != nil {
		return IdentitySecuritySecretProcessResult{}, err
	}
	defer clearIdentitySecurityProcessorKeyRing(&ring)

	if result, found, existingErr := processor.findExistingProcessResult(
		ctx,
		ring,
		request,
		password,
	); found || existingErr != nil {
		return result, existingErr
	}

	activeKey := ring.Keys[ring.ActiveVersion]
	refToken := identitySecurityProcessorRefToken(
		activeKey,
		request.AccountID,
		request.Operation,
		request.IdempotencyKey,
	)
	record := identitySecurityProcessorRecord{
		SchemaVersion:  identitySecurityProcessorRecordSchema,
		AccountID:      request.AccountID,
		Operation:      request.Operation,
		IdempotencyKey: request.IdempotencyKey,
		KeyVersion:     ring.ActiveVersion,
		RequestDigest: identitySecurityProcessorRequestDigest(
			activeKey,
			request.AccountID,
			request.Operation,
			request.IdempotencyKey,
			password,
		),
		SecretRef: "isr_" + refToken,
		CreatedAt: processor.now().UTC().Truncate(time.Microsecond),
	}
	record.LastSecurityTransitionAt = record.CreatedAt
	switch request.Operation {
	case "password_enroll", "password_change", "password_recovery":
		record.PasswordHash, err = processor.passwordHasher.
			HashIdentitySecurityPassword(password)
		if err == nil {
			record.SecretDigest = identitySecurityProcessorSecretDigest(
				activeKey,
				request.AccountID,
				request.Operation,
				record.PasswordHash,
			)
		}
	case "mfa_enroll":
		record.TOTPSecret = make([]byte, 20)
		if _, err = io.ReadFull(processor.random, record.TOTPSecret); err == nil {
			record.SecretDigest = identitySecurityProcessorSecretDigest(
				activeKey,
				request.AccountID,
				request.Operation,
				record.TOTPSecret,
			)
		}
	default:
		err = ErrIdentitySecurityProcessorRejected
	}
	if err != nil {
		clearIdentitySecurityProcessorRecord(&record)
		if errors.Is(err, ErrIdentitySecurityProcessorRejected) {
			return IdentitySecuritySecretProcessResult{}, err
		}
		return IdentitySecuritySecretProcessResult{}, ErrIdentitySecurityProcessorUnavailable
	}
	payload, err := json.Marshal(record)
	if err != nil {
		clearIdentitySecurityProcessorRecord(&record)
		return IdentitySecuritySecretProcessResult{}, ErrIdentitySecurityProcessorUnavailable
	}
	created, err := processor.vault.Create(ctx, refToken, payload)
	clear(payload)
	if err != nil {
		clearIdentitySecurityProcessorRecord(&record)
		return IdentitySecuritySecretProcessResult{}, ErrIdentitySecurityProcessorUnavailable
	}
	if !created {
		clearIdentitySecurityProcessorRecord(&record)
		result, found, retryErr := processor.findExistingProcessResult(
			ctx,
			ring,
			request,
			password,
		)
		if retryErr != nil {
			return IdentitySecuritySecretProcessResult{}, retryErr
		}
		if !found {
			return IdentitySecuritySecretProcessResult{}, ErrIdentitySecurityProcessorUnavailable
		}
		return result, nil
	}
	result := identitySecurityProcessorProcessResult(record, activeKey, refToken)
	clearIdentitySecurityProcessorRecord(&record)
	if !validIdentitySecuritySecretProcessResult(request.Operation, result) {
		return IdentitySecuritySecretProcessResult{}, ErrIdentitySecurityProcessorUnavailable
	}
	return result, nil
}

func (processor *VaultIdentitySecuritySecretProcessor) ConfirmIdentitySecuritySecret(
	ctx context.Context,
	request IdentitySecuritySecretConfirmRequest,
) (IdentitySecuritySecretConfirmResult, error) {
	request.AccountID = strings.TrimSpace(request.AccountID)
	request.ChallengeID = strings.TrimSpace(request.ChallengeID)
	request.Code = strings.TrimSpace(request.Code)
	request.IdempotencyKey = strings.TrimSpace(request.IdempotencyKey)
	if processor == nil || processor.vault == nil || processor.keys == nil ||
		processor.random == nil || processor.now == nil || ctx == nil ||
		!validIdentitySecuritySecretConfirmRequest(request) {
		request.Code = ""
		return IdentitySecuritySecretConfirmResult{}, ErrIdentitySecurityProcessorRejected
	}
	code := []byte(request.Code)
	request.Code = ""
	defer clear(code)
	refToken, tag, ok := parseIdentitySecurityProcessorBoundID(
		request.ChallengeID,
		"isc_",
	)
	if !ok {
		return IdentitySecuritySecretConfirmResult{}, ErrIdentitySecurityProcessorRejected
	}
	ring, err := processor.resolveKeyRing(ctx)
	if err != nil {
		return IdentitySecuritySecretConfirmResult{}, err
	}
	defer clearIdentitySecurityProcessorKeyRing(&ring)

	for attempt := 0; attempt < 8; attempt++ {
		record, version, readErr := processor.readRecord(ctx, refToken)
		if readErr != nil {
			return IdentitySecuritySecretConfirmResult{}, readErr
		}
		recordKey := ring.Keys[record.KeyVersion]
		if len(recordKey) == 0 ||
			record.SchemaVersion != identitySecurityProcessorRecordSchema ||
			record.AccountID != request.AccountID ||
			record.Operation != "mfa_enroll" ||
			subtle.ConstantTimeCompare(
				[]byte(tag),
				[]byte(identitySecurityProcessorBoundTag(
					recordKey,
					"challenge",
					refToken,
					record.AccountID,
					record.Operation,
					record.IdempotencyKey,
				)),
			) != 1 {
			clearIdentitySecurityProcessorRecord(&record)
			return IdentitySecuritySecretConfirmResult{}, ErrIdentitySecurityProcessorRejected
		}
		if record.Confirmed {
			if record.ConfirmIdempotencyKey != request.IdempotencyKey {
				clearIdentitySecurityProcessorRecord(&record)
				return IdentitySecuritySecretConfirmResult{}, ErrIdentitySecurityProcessorRejected
			}
			result := identitySecurityProcessorConfirmResult(
				record,
				recordKey,
				refToken,
			)
			clearIdentitySecurityProcessorRecord(&record)
			if !validIdentitySecuritySecretConfirmResult(result) {
				return IdentitySecuritySecretConfirmResult{}, ErrIdentitySecurityProcessorUnavailable
			}
			return result, nil
		}
		if !validIdentitySecurityTOTPAt(
			record.TOTPSecret,
			code,
			processor.now().UTC(),
		) {
			clearIdentitySecurityProcessorRecord(&record)
			return IdentitySecuritySecretConfirmResult{}, ErrIdentitySecurityProcessorRejected
		}
		recoveryCodes, generateErr := generateIdentitySecurityRecoveryCodes(
			processor.random,
			processor.recoveryCodeCount,
		)
		if generateErr != nil {
			clearIdentitySecurityProcessorRecord(&record)
			return IdentitySecuritySecretConfirmResult{}, ErrIdentitySecurityProcessorUnavailable
		}
		activeKey := ring.Keys[ring.ActiveVersion]
		recoveryDigests := make([]string, 0, len(recoveryCodes))
		for _, recoveryCode := range recoveryCodes {
			recoveryDigests = append(
				recoveryDigests,
				identitySecurityProcessorRecoveryCodeDigest(
					activeKey,
					record.AccountID,
					recoveryCode,
				),
			)
		}
		record.Confirmed = true
		record.ConfirmIdempotencyKey = request.IdempotencyKey
		record.RecoveryKeyVersion = ring.ActiveVersion
		record.RecoveryCodeDigests = recoveryDigests
		record.RecoveryCodes = recoveryCodes
		record.RecoveryBatchDigest = identitySecurityProcessorRecoveryBatchDigest(
			activeKey,
			record.AccountID,
			recoveryDigests,
		)
		record.RecoveryHandoffConsumed = false
		record.LastSecurityTransitionAt = processor.now().UTC().Truncate(time.Microsecond)
		payload, marshalErr := json.Marshal(record)
		if marshalErr != nil {
			clearIdentitySecurityProcessorRecord(&record)
			return IdentitySecuritySecretConfirmResult{}, ErrIdentitySecurityProcessorUnavailable
		}
		swapped, swapErr := processor.vault.CompareAndSwap(
			ctx,
			refToken,
			version,
			payload,
		)
		clear(payload)
		if swapErr != nil {
			clearIdentitySecurityProcessorRecord(&record)
			return IdentitySecuritySecretConfirmResult{}, ErrIdentitySecurityProcessorUnavailable
		}
		if !swapped {
			clearIdentitySecurityProcessorRecord(&record)
			continue
		}
		result := identitySecurityProcessorConfirmResult(record, recordKey, refToken)
		clearIdentitySecurityProcessorRecord(&record)
		if !validIdentitySecuritySecretConfirmResult(result) {
			return IdentitySecuritySecretConfirmResult{}, ErrIdentitySecurityProcessorUnavailable
		}
		return result, nil
	}
	return IdentitySecuritySecretConfirmResult{}, ErrIdentitySecurityProcessorUnavailable
}

func (processor *VaultIdentitySecuritySecretProcessor) PrepareIdentitySecuritySecretMutation(
	ctx context.Context,
	request IdentitySecuritySecretMutationPrepareRequest,
) (IdentitySecuritySecretMutationPrepareResult, error) {
	request.AccountID = strings.TrimSpace(request.AccountID)
	request.Operation = strings.TrimSpace(request.Operation)
	request.IdempotencyKey = strings.TrimSpace(request.IdempotencyKey)
	request.SecretRef = strings.TrimSpace(request.SecretRef)
	request.SecretDigest = strings.TrimSpace(request.SecretDigest)
	request.ExpectedRecoveryBatchDigest = strings.TrimSpace(
		request.ExpectedRecoveryBatchDigest,
	)
	request.RecoveryCode = strings.TrimSpace(request.RecoveryCode)
	if processor == nil || processor.vault == nil || processor.keys == nil ||
		processor.random == nil || processor.now == nil || ctx == nil ||
		!validIdentitySecuritySecretMutationPrepareRequest(request) {
		request.RecoveryCode = ""
		return IdentitySecuritySecretMutationPrepareResult{},
			ErrIdentitySecurityProcessorRejected
	}
	recoveryCode := []byte(request.RecoveryCode)
	request.RecoveryCode = ""
	defer clear(recoveryCode)
	refToken, ok := parseIdentitySecurityProcessorSecretRef(request.SecretRef)
	if !ok {
		return IdentitySecuritySecretMutationPrepareResult{},
			ErrIdentitySecurityProcessorRejected
	}
	ring, err := processor.resolveKeyRing(ctx)
	if err != nil {
		return IdentitySecuritySecretMutationPrepareResult{}, err
	}
	defer clearIdentitySecurityProcessorKeyRing(&ring)
	activeKey := ring.Keys[ring.ActiveVersion]
	requestDigest := identitySecurityProcessorMutationRequestDigest(
		activeKey,
		request,
		recoveryCode,
	)

	for attempt := 0; attempt < 8; attempt++ {
		record, version, readErr := processor.readRecord(ctx, refToken)
		if readErr != nil {
			return IdentitySecuritySecretMutationPrepareResult{}, readErr
		}
		recordKey := ring.Keys[record.KeyVersion]
		if len(recordKey) == 0 ||
			record.AccountID != request.AccountID ||
			record.Operation != "mfa_enroll" ||
			record.SecretRef != request.SecretRef ||
			subtle.ConstantTimeCompare(
				[]byte(record.SecretDigest),
				[]byte(request.SecretDigest),
			) != 1 {
			clearIdentitySecurityProcessorRecord(&record)
			return IdentitySecuritySecretMutationPrepareResult{},
				ErrIdentitySecurityProcessorRejected
		}

		if record.PendingOperation != "" {
			pendingKey := ring.Keys[record.PendingKeyVersion]
			if len(pendingKey) != 0 &&
				record.PendingOperation == request.Operation &&
				record.PendingIdempotencyKey == request.IdempotencyKey &&
				subtle.ConstantTimeCompare(
					[]byte(record.PendingRequestDigest),
					[]byte(identitySecurityProcessorMutationRequestDigest(
						pendingKey,
						request,
						recoveryCode,
					)),
				) == 1 {
				result := identitySecurityProcessorMutationPrepareResult(
					record,
					pendingKey,
					refToken,
				)
				clearIdentitySecurityProcessorRecord(&record)
				if !validIdentitySecuritySecretMutationPrepareResult(
					request.Operation,
					result,
				) {
					return IdentitySecuritySecretMutationPrepareResult{},
						ErrIdentitySecurityProcessorUnavailable
				}
				return result, nil
			}
			if !record.PendingFinalized ||
				(record.PendingOperation == "mfa_recovery_rotate" &&
					!record.RecoveryHandoffConsumed) {
				clearIdentitySecurityProcessorRecord(&record)
				return IdentitySecuritySecretMutationPrepareResult{},
					ErrIdentitySecurityProcessorRejected
			}
			clearIdentitySecurityProcessorPendingMutation(&record)
		}

		recoveryKey := ring.Keys[record.RecoveryKeyVersion]
		if len(recoveryKey) == 0 ||
			!record.Confirmed || !record.RecoveryHandoffConsumed ||
			len(record.RecoveryCodes) != 0 ||
			subtle.ConstantTimeCompare(
				[]byte(record.RecoveryBatchDigest),
				[]byte(request.ExpectedRecoveryBatchDigest),
			) != 1 ||
			len(record.RecoveryCodeDigests) != request.ExpectedRecoveryCodeCount {
			clearIdentitySecurityProcessorRecord(&record)
			return IdentitySecuritySecretMutationPrepareResult{},
				ErrIdentitySecurityProcessorRejected
		}

		record.PreviousConfirmed = record.Confirmed
		record.PreviousTOTPSecret = append(
			[]byte(nil),
			record.TOTPSecret...,
		)
		record.PreviousRecoveryVersion = record.RecoveryKeyVersion
		record.PreviousRecoveryBatch = record.RecoveryBatchDigest
		record.PreviousRecoveryDigests = append(
			[]string(nil),
			record.RecoveryCodeDigests...,
		)
		record.PreviousRecoveryCodes = cloneIdentitySecurityProcessorByteSlices(
			record.RecoveryCodes,
		)
		record.PreviousHandoffConsumed = record.RecoveryHandoffConsumed
		record.PendingOperation = request.Operation
		record.PendingIdempotencyKey = request.IdempotencyKey
		record.PendingRequestDigest = requestDigest
		record.PendingKeyVersion = ring.ActiveVersion
		record.PendingExpectedBatch = request.ExpectedRecoveryBatchDigest
		record.PendingExpectedCount = request.ExpectedRecoveryCodeCount
		record.PendingFinalized = false

		switch request.Operation {
		case "mfa_recovery_consume":
			candidateDigest := identitySecurityProcessorRecoveryCodeDigest(
				recoveryKey,
				record.AccountID,
				recoveryCode,
			)
			matchedIndex := -1
			matched := 0
			for index, digest := range record.RecoveryCodeDigests {
				equal := subtle.ConstantTimeCompare(
					[]byte(digest),
					[]byte(candidateDigest),
				)
				if equal == 1 && matchedIndex < 0 {
					matchedIndex = index
				}
				matched |= equal
			}
			if matched != 1 || matchedIndex < 0 {
				clearIdentitySecurityProcessorRecord(&record)
				return IdentitySecuritySecretMutationPrepareResult{},
					ErrIdentitySecurityProcessorRejected
			}
			record.RecoveryCodeDigests = append(
				record.RecoveryCodeDigests[:matchedIndex:matchedIndex],
				record.RecoveryCodeDigests[matchedIndex+1:]...,
			)
			record.RecoveryBatchDigest =
				identitySecurityProcessorRecoveryBatchDigest(
					recoveryKey,
					record.AccountID,
					record.RecoveryCodeDigests,
				)
		case "mfa_recovery_rotate":
			recoveryCodes, generateErr := generateIdentitySecurityRecoveryCodes(
				processor.random,
				processor.recoveryCodeCount,
			)
			if generateErr != nil {
				clearIdentitySecurityProcessorRecord(&record)
				return IdentitySecuritySecretMutationPrepareResult{},
					ErrIdentitySecurityProcessorUnavailable
			}
			recoveryDigests := make([]string, 0, len(recoveryCodes))
			for _, code := range recoveryCodes {
				recoveryDigests = append(
					recoveryDigests,
					identitySecurityProcessorRecoveryCodeDigest(
						activeKey,
						record.AccountID,
						code,
					),
				)
			}
			record.RecoveryKeyVersion = ring.ActiveVersion
			record.RecoveryCodeDigests = recoveryDigests
			record.RecoveryCodes = recoveryCodes
			record.RecoveryBatchDigest =
				identitySecurityProcessorRecoveryBatchDigest(
					activeKey,
					record.AccountID,
					recoveryDigests,
				)
			record.RecoveryHandoffConsumed = false
		case "mfa_disable":
			record.Confirmed = false
			clear(record.TOTPSecret)
			record.TOTPSecret = nil
			record.RecoveryKeyVersion = ""
			record.RecoveryBatchDigest = ""
			record.RecoveryCodeDigests = nil
			clearIdentitySecurityProcessorByteSlices(record.RecoveryCodes)
			record.RecoveryCodes = nil
			record.RecoveryHandoffConsumed = false
		default:
			clearIdentitySecurityProcessorRecord(&record)
			return IdentitySecuritySecretMutationPrepareResult{},
				ErrIdentitySecurityProcessorRejected
		}
		record.LastSecurityTransitionAt = processor.now().UTC().
			Truncate(time.Microsecond)
		payload, marshalErr := json.Marshal(record)
		if marshalErr != nil {
			clearIdentitySecurityProcessorRecord(&record)
			return IdentitySecuritySecretMutationPrepareResult{},
				ErrIdentitySecurityProcessorUnavailable
		}
		swapped, swapErr := processor.vault.CompareAndSwap(
			ctx,
			refToken,
			version,
			payload,
		)
		clear(payload)
		if swapErr != nil {
			clearIdentitySecurityProcessorRecord(&record)
			return IdentitySecuritySecretMutationPrepareResult{},
				ErrIdentitySecurityProcessorUnavailable
		}
		if !swapped {
			clearIdentitySecurityProcessorRecord(&record)
			continue
		}
		result := identitySecurityProcessorMutationPrepareResult(
			record,
			activeKey,
			refToken,
		)
		clearIdentitySecurityProcessorRecord(&record)
		if !validIdentitySecuritySecretMutationPrepareResult(
			request.Operation,
			result,
		) {
			return IdentitySecuritySecretMutationPrepareResult{},
				ErrIdentitySecurityProcessorUnavailable
		}
		return result, nil
	}
	return IdentitySecuritySecretMutationPrepareResult{},
		ErrIdentitySecurityProcessorUnavailable
}

func (processor *VaultIdentitySecuritySecretProcessor) FinalizeIdentitySecuritySecretMutation(
	ctx context.Context,
	request IdentitySecuritySecretMutationFinalizeRequest,
) error {
	request.AccountID = strings.TrimSpace(request.AccountID)
	request.Operation = strings.TrimSpace(request.Operation)
	request.IdempotencyKey = strings.TrimSpace(request.IdempotencyKey)
	request.FinalizeToken = strings.TrimSpace(request.FinalizeToken)
	if processor == nil || processor.vault == nil || processor.keys == nil ||
		processor.now == nil || ctx == nil ||
		!validIdentitySecuritySecretMutationFinalizeRequest(request) {
		return ErrIdentitySecurityProcessorRejected
	}
	refToken, tag, ok := parseIdentitySecurityProcessorBoundID(
		request.FinalizeToken,
		"isf_",
	)
	if !ok {
		return ErrIdentitySecurityProcessorRejected
	}
	callCtx := context.WithoutCancel(ctx)
	ring, err := processor.resolveKeyRing(callCtx)
	if err != nil {
		return err
	}
	defer clearIdentitySecurityProcessorKeyRing(&ring)
	if !identitySecurityProcessorBoundTagMatches(
		ring,
		tag,
		"finalize",
		refToken,
		request.AccountID,
		request.Operation,
		request.IdempotencyKey,
	) {
		return ErrIdentitySecurityProcessorRejected
	}

	for attempt := 0; attempt < 8; attempt++ {
		record, version, readErr := processor.readRecord(callCtx, refToken)
		if errors.Is(readErr, ErrIdentitySecurityProcessorRejected) &&
			request.Operation == "mfa_disable" {
			return nil
		}
		if readErr != nil {
			return readErr
		}
		pendingKey := ring.Keys[record.PendingKeyVersion]
		if len(pendingKey) == 0 ||
			record.AccountID != request.AccountID ||
			record.PendingOperation != request.Operation ||
			record.PendingIdempotencyKey != request.IdempotencyKey ||
			subtle.ConstantTimeCompare(
				[]byte(tag),
				[]byte(identitySecurityProcessorBoundTag(
					pendingKey,
					"finalize",
					refToken,
					record.AccountID,
					record.PendingOperation,
					record.PendingIdempotencyKey,
				)),
			) != 1 {
			clearIdentitySecurityProcessorRecord(&record)
			return ErrIdentitySecurityProcessorRejected
		}
		if record.PendingFinalized {
			if request.Operation == "mfa_disable" {
				clearIdentitySecurityProcessorRecord(&record)
				if err := processor.vault.Delete(callCtx, refToken); err != nil {
					return ErrIdentitySecurityProcessorUnavailable
				}
				return nil
			}
			clearIdentitySecurityProcessorRecord(&record)
			return nil
		}
		record.PendingFinalized = true
		clearIdentitySecurityProcessorPendingBackup(&record)
		record.LastSecurityTransitionAt = processor.now().UTC().
			Truncate(time.Microsecond)
		payload, marshalErr := json.Marshal(record)
		if marshalErr != nil {
			clearIdentitySecurityProcessorRecord(&record)
			return ErrIdentitySecurityProcessorUnavailable
		}
		swapped, swapErr := processor.vault.CompareAndSwap(
			callCtx,
			refToken,
			version,
			payload,
		)
		clear(payload)
		clearIdentitySecurityProcessorRecord(&record)
		if swapErr != nil {
			return ErrIdentitySecurityProcessorUnavailable
		}
		if swapped {
			if request.Operation == "mfa_disable" {
				if err := processor.vault.Delete(callCtx, refToken); err != nil {
					return ErrIdentitySecurityProcessorUnavailable
				}
			}
			return nil
		}
	}
	return ErrIdentitySecurityProcessorUnavailable
}

func (processor *VaultIdentitySecuritySecretProcessor) ConsumeIdentitySecuritySecretHandoff(
	ctx context.Context,
	request IdentitySecuritySecretHandoffRequest,
) (IdentitySecuritySecretHandoff, error) {
	request.AccountID = strings.TrimSpace(request.AccountID)
	request.Operation = strings.TrimSpace(request.Operation)
	request.IdempotencyKey = strings.TrimSpace(request.IdempotencyKey)
	request.HandoffID = strings.TrimSpace(request.HandoffID)
	if processor == nil || processor.vault == nil || processor.keys == nil ||
		processor.now == nil || ctx == nil ||
		!validIdentitySecuritySecretHandoffRequest(request) {
		return IdentitySecuritySecretHandoff{}, ErrIdentitySecurityProcessorRejected
	}
	refToken, tag, ok := parseIdentitySecurityProcessorBoundID(
		request.HandoffID,
		"ish_",
	)
	if !ok {
		return IdentitySecuritySecretHandoff{}, ErrIdentitySecurityProcessorRejected
	}
	ring, err := processor.resolveKeyRing(ctx)
	if err != nil {
		return IdentitySecuritySecretHandoff{}, err
	}
	defer clearIdentitySecurityProcessorKeyRing(&ring)

	for attempt := 0; attempt < 8; attempt++ {
		record, version, readErr := processor.readRecord(ctx, refToken)
		if readErr != nil {
			return IdentitySecuritySecretHandoff{}, readErr
		}
		recordKey := ring.Keys[record.KeyVersion]
		purpose := "provisioning"
		expectedIdempotency := record.IdempotencyKey
		if request.Operation == "mfa_confirm" {
			purpose = "recovery"
			expectedIdempotency = record.ConfirmIdempotencyKey
		} else if request.Operation == "mfa_recovery_rotate" {
			recordKey = ring.Keys[record.PendingKeyVersion]
			purpose = "recovery-rotate"
			expectedIdempotency = record.PendingIdempotencyKey
		}
		if len(recordKey) == 0 ||
			record.AccountID != request.AccountID ||
			record.Operation != "mfa_enroll" ||
			expectedIdempotency == "" ||
			expectedIdempotency != request.IdempotencyKey ||
			subtle.ConstantTimeCompare(
				[]byte(tag),
				[]byte(identitySecurityProcessorBoundTag(
					recordKey,
					purpose,
					refToken,
					record.AccountID,
					request.Operation,
					expectedIdempotency,
				)),
			) != 1 {
			clearIdentitySecurityProcessorRecord(&record)
			return IdentitySecuritySecretHandoff{}, ErrIdentitySecurityProcessorRejected
		}

		var handoff IdentitySecuritySecretHandoff
		switch request.Operation {
		case "mfa_enroll":
			if record.ProvisioningConsumed || len(record.TOTPSecret) != 20 {
				clearIdentitySecurityProcessorRecord(&record)
				return IdentitySecuritySecretHandoff{}, ErrIdentitySecurityProcessorRejected
			}
			handoff.ProvisioningURI = identitySecurityProcessorProvisioningURI(
				processor.issuer,
				record.AccountID,
				record.TOTPSecret,
			)
			record.ProvisioningConsumed = true
		case "mfa_confirm":
			if !record.Confirmed || record.RecoveryHandoffConsumed ||
				len(record.RecoveryCodes) < 6 {
				clearIdentitySecurityProcessorRecord(&record)
				return IdentitySecuritySecretHandoff{}, ErrIdentitySecurityProcessorRejected
			}
			handoff.RecoveryCodes = make([]string, 0, len(record.RecoveryCodes))
			for _, recoveryCode := range record.RecoveryCodes {
				handoff.RecoveryCodes = append(
					handoff.RecoveryCodes,
					string(recoveryCode),
				)
			}
			record.RecoveryHandoffConsumed = true
			clearIdentitySecurityProcessorByteSlices(record.RecoveryCodes)
			record.RecoveryCodes = nil
		case "mfa_recovery_rotate":
			if record.PendingOperation != "mfa_recovery_rotate" ||
				!record.PendingFinalized || record.RecoveryHandoffConsumed ||
				len(record.RecoveryCodes) < 6 {
				clearIdentitySecurityProcessorRecord(&record)
				return IdentitySecuritySecretHandoff{},
					ErrIdentitySecurityProcessorRejected
			}
			handoff.RecoveryCodes = make(
				[]string,
				0,
				len(record.RecoveryCodes),
			)
			for _, recoveryCode := range record.RecoveryCodes {
				handoff.RecoveryCodes = append(
					handoff.RecoveryCodes,
					string(recoveryCode),
				)
			}
			record.RecoveryHandoffConsumed = true
			clearIdentitySecurityProcessorByteSlices(record.RecoveryCodes)
			record.RecoveryCodes = nil
			clearIdentitySecurityProcessorPendingMutation(&record)
		default:
			clearIdentitySecurityProcessorRecord(&record)
			return IdentitySecuritySecretHandoff{}, ErrIdentitySecurityProcessorRejected
		}
		record.LastSecurityTransitionAt = processor.now().UTC().Truncate(time.Microsecond)
		payload, marshalErr := json.Marshal(record)
		if marshalErr != nil {
			clearIdentitySecurityProcessorRecord(&record)
			clearIdentitySecuritySecretHandoff(&handoff)
			return IdentitySecuritySecretHandoff{}, ErrIdentitySecurityProcessorUnavailable
		}
		swapped, swapErr := processor.vault.CompareAndSwap(
			ctx,
			refToken,
			version,
			payload,
		)
		clear(payload)
		clearIdentitySecurityProcessorRecord(&record)
		if swapErr != nil {
			clearIdentitySecuritySecretHandoff(&handoff)
			return IdentitySecuritySecretHandoff{}, ErrIdentitySecurityProcessorUnavailable
		}
		if !swapped {
			clearIdentitySecuritySecretHandoff(&handoff)
			continue
		}
		if !validIdentitySecuritySecretHandoff(request.Operation, handoff) {
			clearIdentitySecuritySecretHandoff(&handoff)
			return IdentitySecuritySecretHandoff{}, ErrIdentitySecurityProcessorUnavailable
		}
		return handoff, nil
	}
	return IdentitySecuritySecretHandoff{}, ErrIdentitySecurityProcessorUnavailable
}

func (processor *VaultIdentitySecuritySecretProcessor) CleanupIdentitySecuritySecret(
	ctx context.Context,
	request IdentitySecuritySecretCleanupRequest,
) error {
	request.AccountID = strings.TrimSpace(request.AccountID)
	request.Operation = strings.TrimSpace(request.Operation)
	request.IdempotencyKey = strings.TrimSpace(request.IdempotencyKey)
	request.CleanupToken = strings.TrimSpace(request.CleanupToken)
	if processor == nil || processor.vault == nil || processor.keys == nil ||
		processor.now == nil || ctx == nil ||
		!validIdentitySecuritySecretCleanupRequest(request) {
		return ErrIdentitySecurityProcessorRejected
	}
	refToken, tag, ok := parseIdentitySecurityProcessorBoundID(
		request.CleanupToken,
		"isx_",
	)
	if !ok {
		return ErrIdentitySecurityProcessorRejected
	}
	ring, err := processor.resolveKeyRing(context.WithoutCancel(ctx))
	if err != nil {
		return err
	}
	defer clearIdentitySecurityProcessorKeyRing(&ring)
	if !identitySecurityProcessorBoundTagMatches(
		ring,
		tag,
		"cleanup",
		refToken,
		request.AccountID,
		request.Operation,
		request.IdempotencyKey,
	) {
		return ErrIdentitySecurityProcessorRejected
	}

	for attempt := 0; attempt < 8; attempt++ {
		record, version, readErr := processor.readRecord(
			context.WithoutCancel(ctx),
			refToken,
		)
		if errors.Is(readErr, ErrIdentitySecurityProcessorRejected) {
			return nil
		}
		if readErr != nil {
			return readErr
		}
		if request.Operation == "mfa_recovery_consume" ||
			request.Operation == "mfa_recovery_rotate" ||
			request.Operation == "mfa_disable" {
			if record.PendingOperation == "" {
				clearIdentitySecurityProcessorRecord(&record)
				return nil
			}
			pendingKey := ring.Keys[record.PendingKeyVersion]
			if len(pendingKey) == 0 ||
				record.AccountID != request.AccountID ||
				record.PendingOperation != request.Operation ||
				record.PendingIdempotencyKey != request.IdempotencyKey ||
				subtle.ConstantTimeCompare(
					[]byte(tag),
					[]byte(identitySecurityProcessorBoundTag(
						pendingKey,
						"cleanup",
						refToken,
						record.AccountID,
						record.PendingOperation,
						record.PendingIdempotencyKey,
					)),
				) != 1 ||
				record.PendingFinalized {
				clearIdentitySecurityProcessorRecord(&record)
				return ErrIdentitySecurityProcessorRejected
			}
			restoreIdentitySecurityProcessorPendingMutation(&record)
			record.LastSecurityTransitionAt = processor.now().UTC().
				Truncate(time.Microsecond)
			payload, marshalErr := json.Marshal(record)
			if marshalErr != nil {
				clearIdentitySecurityProcessorRecord(&record)
				return ErrIdentitySecurityProcessorUnavailable
			}
			swapped, swapErr := processor.vault.CompareAndSwap(
				context.WithoutCancel(ctx),
				refToken,
				version,
				payload,
			)
			clear(payload)
			clearIdentitySecurityProcessorRecord(&record)
			if swapErr != nil {
				return ErrIdentitySecurityProcessorUnavailable
			}
			if swapped {
				return nil
			}
			continue
		}
		recordKey := ring.Keys[record.KeyVersion]
		expectedIdempotency := record.IdempotencyKey
		if request.Operation == "mfa_confirm" {
			expectedIdempotency = record.ConfirmIdempotencyKey
		}
		if len(recordKey) == 0 ||
			record.AccountID != request.AccountID ||
			expectedIdempotency == "" ||
			expectedIdempotency != request.IdempotencyKey ||
			subtle.ConstantTimeCompare(
				[]byte(tag),
				[]byte(identitySecurityProcessorBoundTag(
					recordKey,
					"cleanup",
					refToken,
					record.AccountID,
					request.Operation,
					expectedIdempotency,
				)),
			) != 1 {
			clearIdentitySecurityProcessorRecord(&record)
			return ErrIdentitySecurityProcessorRejected
		}
		if request.Operation != "mfa_confirm" {
			clearIdentitySecurityProcessorRecord(&record)
			if err := processor.vault.Delete(
				context.WithoutCancel(ctx),
				refToken,
			); err != nil {
				return ErrIdentitySecurityProcessorUnavailable
			}
			return nil
		}
		record.Confirmed = false
		record.ConfirmIdempotencyKey = ""
		record.RecoveryKeyVersion = ""
		record.RecoveryBatchDigest = ""
		record.RecoveryCodeDigests = nil
		clearIdentitySecurityProcessorByteSlices(record.RecoveryCodes)
		record.RecoveryCodes = nil
		record.RecoveryHandoffConsumed = false
		record.LastSecurityTransitionAt = processor.now().UTC().Truncate(time.Microsecond)
		payload, marshalErr := json.Marshal(record)
		if marshalErr != nil {
			clearIdentitySecurityProcessorRecord(&record)
			return ErrIdentitySecurityProcessorUnavailable
		}
		swapped, swapErr := processor.vault.CompareAndSwap(
			context.WithoutCancel(ctx),
			refToken,
			version,
			payload,
		)
		clear(payload)
		clearIdentitySecurityProcessorRecord(&record)
		if swapErr != nil {
			return ErrIdentitySecurityProcessorUnavailable
		}
		if swapped {
			return nil
		}
	}
	return ErrIdentitySecurityProcessorUnavailable
}

func (processor *VaultIdentitySecuritySecretProcessor) findExistingProcessResult(
	ctx context.Context,
	ring IdentitySecurityProcessorKeyRing,
	request IdentitySecuritySecretProcessRequest,
	password []byte,
) (IdentitySecuritySecretProcessResult, bool, error) {
	for _, keyVersion := range identitySecurityProcessorKeyVersions(ring) {
		key := ring.Keys[keyVersion]
		refToken := identitySecurityProcessorRefToken(
			key,
			request.AccountID,
			request.Operation,
			request.IdempotencyKey,
		)
		record, _, err := processor.readRecord(ctx, refToken)
		if errors.Is(err, ErrIdentitySecurityProcessorRejected) {
			continue
		}
		if err != nil {
			return IdentitySecuritySecretProcessResult{}, false, err
		}
		recordKey := ring.Keys[record.KeyVersion]
		expectedRequestDigest := identitySecurityProcessorRequestDigest(
			recordKey,
			request.AccountID,
			request.Operation,
			request.IdempotencyKey,
			password,
		)
		if len(recordKey) == 0 ||
			record.AccountID != request.AccountID ||
			record.Operation != request.Operation ||
			record.IdempotencyKey != request.IdempotencyKey ||
			record.SecretRef != "isr_"+refToken ||
			subtle.ConstantTimeCompare(
				[]byte(record.RequestDigest),
				[]byte(expectedRequestDigest),
			) != 1 {
			clearIdentitySecurityProcessorRecord(&record)
			return IdentitySecuritySecretProcessResult{}, true,
				ErrIdentitySecurityProcessorRejected
		}
		result := identitySecurityProcessorProcessResult(record, recordKey, refToken)
		clearIdentitySecurityProcessorRecord(&record)
		if !validIdentitySecuritySecretProcessResult(request.Operation, result) {
			return IdentitySecuritySecretProcessResult{}, true,
				ErrIdentitySecurityProcessorUnavailable
		}
		return result, true, nil
	}
	return IdentitySecuritySecretProcessResult{}, false, nil
}

func (processor *VaultIdentitySecuritySecretProcessor) resolveKeyRing(
	ctx context.Context,
) (IdentitySecurityProcessorKeyRing, error) {
	ring, err := processor.keys.ResolveIdentitySecurityProcessorKeys(ctx)
	if err != nil {
		clearIdentitySecurityProcessorKeyRing(&ring)
		return IdentitySecurityProcessorKeyRing{}, ErrIdentitySecurityProcessorUnavailable
	}
	ring.ActiveVersion = strings.TrimSpace(ring.ActiveVersion)
	if !identitySecurityProcessorKeyVersionPattern.MatchString(ring.ActiveVersion) ||
		len(ring.Keys) < 1 || len(ring.Keys) > 8 {
		clearIdentitySecurityProcessorKeyRing(&ring)
		return IdentitySecurityProcessorKeyRing{}, ErrIdentitySecurityProcessorUnavailable
	}
	copyRing := IdentitySecurityProcessorKeyRing{
		ActiveVersion: ring.ActiveVersion,
		Keys:          make(map[string][]byte, len(ring.Keys)),
	}
	for version, key := range ring.Keys {
		version = strings.TrimSpace(version)
		if !identitySecurityProcessorKeyVersionPattern.MatchString(version) ||
			len(key) < 32 || len(key) > 64 {
			clearIdentitySecurityProcessorKeyRing(&ring)
			clearIdentitySecurityProcessorKeyRing(&copyRing)
			return IdentitySecurityProcessorKeyRing{}, ErrIdentitySecurityProcessorUnavailable
		}
		copyRing.Keys[version] = append([]byte(nil), key...)
	}
	clearIdentitySecurityProcessorKeyRing(&ring)
	if len(copyRing.Keys[copyRing.ActiveVersion]) == 0 {
		clearIdentitySecurityProcessorKeyRing(&copyRing)
		return IdentitySecurityProcessorKeyRing{}, ErrIdentitySecurityProcessorUnavailable
	}
	return copyRing, nil
}

func (processor *VaultIdentitySecuritySecretProcessor) readRecord(
	ctx context.Context,
	refToken string,
) (identitySecurityProcessorRecord, uint64, error) {
	payload, version, err := processor.vault.Read(ctx, refToken)
	if errors.Is(err, ErrIdentitySecurityProcessorVaultRecordNotFound) {
		return identitySecurityProcessorRecord{}, 0, ErrIdentitySecurityProcessorRejected
	}
	if err != nil || version == 0 || len(payload) == 0 || len(payload) > 256*1024 {
		clear(payload)
		return identitySecurityProcessorRecord{}, 0, ErrIdentitySecurityProcessorUnavailable
	}
	defer clear(payload)
	var record identitySecurityProcessorRecord
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.DisallowUnknownFields()
	if decodeErr := decoder.Decode(&record); decodeErr != nil {
		clearIdentitySecurityProcessorRecord(&record)
		return identitySecurityProcessorRecord{}, 0, ErrIdentitySecurityProcessorUnavailable
	}
	if decodeErr := decoder.Decode(&struct{}{}); !errors.Is(decodeErr, io.EOF) {
		clearIdentitySecurityProcessorRecord(&record)
		return identitySecurityProcessorRecord{}, 0, ErrIdentitySecurityProcessorUnavailable
	}
	if record.SchemaVersion != identitySecurityProcessorRecordSchema ||
		!validPostgresIdentityVerificationUUID(record.AccountID) ||
		(record.Operation != "password_enroll" &&
			record.Operation != "password_change" &&
			record.Operation != "password_recovery" &&
			record.Operation != "mfa_enroll") ||
		!validIdentitySecurityIdempotencyKey(record.IdempotencyKey) ||
		!identitySecurityProcessorKeyVersionPattern.MatchString(record.KeyVersion) ||
		!validIdentitySecurityDigest(record.RequestDigest) ||
		!identitySecurityProcessorReferencePattern.MatchString(record.SecretRef) ||
		!validIdentitySecurityDigest(record.SecretDigest) ||
		record.CreatedAt.IsZero() || record.LastSecurityTransitionAt.IsZero() {
		clearIdentitySecurityProcessorRecord(&record)
		return identitySecurityProcessorRecord{}, 0, ErrIdentitySecurityProcessorUnavailable
	}
	return record, version, nil
}

func identitySecurityProcessorProcessResult(
	record identitySecurityProcessorRecord,
	key []byte,
	refToken string,
) IdentitySecuritySecretProcessResult {
	result := IdentitySecuritySecretProcessResult{
		SecretRef:    record.SecretRef,
		SecretDigest: record.SecretDigest,
		KeyVersion:   record.KeyVersion,
		CleanupToken: identitySecurityProcessorBoundID(
			"isx_",
			key,
			"cleanup",
			refToken,
			record.AccountID,
			record.Operation,
			record.IdempotencyKey,
		),
	}
	if record.Operation == "mfa_enroll" {
		result.ConfirmationChallengeID = identitySecurityProcessorBoundID(
			"isc_",
			key,
			"challenge",
			refToken,
			record.AccountID,
			record.Operation,
			record.IdempotencyKey,
		)
		result.HandoffID = identitySecurityProcessorBoundID(
			"ish_",
			key,
			"provisioning",
			refToken,
			record.AccountID,
			record.Operation,
			record.IdempotencyKey,
		)
	}
	return result
}

func identitySecurityProcessorConfirmResult(
	record identitySecurityProcessorRecord,
	recordKey []byte,
	refToken string,
) IdentitySecuritySecretConfirmResult {
	return IdentitySecuritySecretConfirmResult{
		RecoveryBatchDigest: record.RecoveryBatchDigest,
		RecoveryCodeCount:   len(record.RecoveryCodeDigests),
		KeyVersion:          record.RecoveryKeyVersion,
		HandoffID: identitySecurityProcessorBoundID(
			"ish_",
			recordKey,
			"recovery",
			refToken,
			record.AccountID,
			"mfa_confirm",
			record.ConfirmIdempotencyKey,
		),
		CleanupToken: identitySecurityProcessorBoundID(
			"isx_",
			recordKey,
			"cleanup",
			refToken,
			record.AccountID,
			"mfa_confirm",
			record.ConfirmIdempotencyKey,
		),
	}
}

func identitySecurityProcessorMutationPrepareResult(
	record identitySecurityProcessorRecord,
	pendingKey []byte,
	refToken string,
) IdentitySecuritySecretMutationPrepareResult {
	keyVersion := record.RecoveryKeyVersion
	if record.PendingOperation == "mfa_disable" {
		keyVersion = record.PendingKeyVersion
	}
	result := IdentitySecuritySecretMutationPrepareResult{
		SecretRef:                   record.SecretRef,
		SecretDigest:                record.SecretDigest,
		ExpectedRecoveryBatchDigest: record.PendingExpectedBatch,
		ExpectedRecoveryCodeCount:   record.PendingExpectedCount,
		RecoveryBatchDigest:         record.RecoveryBatchDigest,
		RecoveryCodeCount:           len(record.RecoveryCodeDigests),
		KeyVersion:                  keyVersion,
		FinalizeToken: identitySecurityProcessorBoundID(
			"isf_",
			pendingKey,
			"finalize",
			refToken,
			record.AccountID,
			record.PendingOperation,
			record.PendingIdempotencyKey,
		),
		CleanupToken: identitySecurityProcessorBoundID(
			"isx_",
			pendingKey,
			"cleanup",
			refToken,
			record.AccountID,
			record.PendingOperation,
			record.PendingIdempotencyKey,
		),
	}
	if record.PendingOperation == "mfa_recovery_rotate" {
		result.HandoffID = identitySecurityProcessorBoundID(
			"ish_",
			pendingKey,
			"recovery-rotate",
			refToken,
			record.AccountID,
			record.PendingOperation,
			record.PendingIdempotencyKey,
		)
	}
	return result
}

func identitySecurityProcessorRefToken(
	key []byte,
	accountID string,
	operation string,
	idempotencyKey string,
) string {
	return base64.RawURLEncoding.EncodeToString(identitySecurityProcessorHMAC(
		key,
		"reference",
		accountID,
		operation,
		idempotencyKey,
	))
}

func parseIdentitySecurityProcessorSecretRef(value string) (string, bool) {
	if !strings.HasPrefix(value, "isr_") {
		return "", false
	}
	refToken := strings.TrimPrefix(value, "isr_")
	if len(refToken) != identitySecurityProcessorRefTokenSize {
		return "", false
	}
	if _, err := base64.RawURLEncoding.Strict().DecodeString(refToken); err != nil {
		return "", false
	}
	return refToken, true
}

func identitySecurityProcessorBoundID(
	prefix string,
	key []byte,
	purpose string,
	refToken string,
	accountID string,
	operation string,
	idempotencyKey string,
) string {
	return prefix + refToken + identitySecurityProcessorBoundTag(
		key,
		purpose,
		refToken,
		accountID,
		operation,
		idempotencyKey,
	)
}

func identitySecurityProcessorBoundTag(
	key []byte,
	purpose string,
	refToken string,
	accountID string,
	operation string,
	idempotencyKey string,
) string {
	digest := identitySecurityProcessorHMAC(
		key,
		"bound-"+purpose,
		refToken,
		accountID,
		operation,
		idempotencyKey,
	)
	return base64.RawURLEncoding.EncodeToString(digest[:16])
}

func identitySecurityProcessorBoundTagMatches(
	ring IdentitySecurityProcessorKeyRing,
	actualTag string,
	purpose string,
	refToken string,
	accountID string,
	operation string,
	idempotencyKey string,
) bool {
	matched := 0
	for _, keyVersion := range identitySecurityProcessorKeyVersions(ring) {
		expectedTag := identitySecurityProcessorBoundTag(
			ring.Keys[keyVersion],
			purpose,
			refToken,
			accountID,
			operation,
			idempotencyKey,
		)
		matched |= subtle.ConstantTimeCompare(
			[]byte(actualTag),
			[]byte(expectedTag),
		)
	}
	return matched == 1
}

func parseIdentitySecurityProcessorBoundID(
	value string,
	prefix string,
) (string, string, bool) {
	if !strings.HasPrefix(value, prefix) {
		return "", "", false
	}
	body := strings.TrimPrefix(value, prefix)
	if len(body) != identitySecurityProcessorRefTokenSize+
		identitySecurityProcessorTagSize {
		return "", "", false
	}
	refToken := body[:identitySecurityProcessorRefTokenSize]
	tag := body[identitySecurityProcessorRefTokenSize:]
	if _, err := base64.RawURLEncoding.Strict().DecodeString(refToken); err != nil {
		return "", "", false
	}
	if _, err := base64.RawURLEncoding.Strict().DecodeString(tag); err != nil {
		return "", "", false
	}
	return refToken, tag, true
}

func identitySecurityProcessorRequestDigest(
	key []byte,
	accountID string,
	operation string,
	idempotencyKey string,
	password []byte,
) string {
	mac := hmac.New(sha256.New, key)
	identitySecurityProcessorWriteCanonical(
		mac,
		"request",
		accountID,
		operation,
		idempotencyKey,
	)
	_, _ = mac.Write(password)
	return hex.EncodeToString(mac.Sum(nil))
}

func identitySecurityProcessorMutationRequestDigest(
	key []byte,
	request IdentitySecuritySecretMutationPrepareRequest,
	recoveryCode []byte,
) string {
	mac := hmac.New(sha256.New, key)
	identitySecurityProcessorWriteCanonical(
		mac,
		"mutation-request",
		request.AccountID,
		request.Operation,
		request.IdempotencyKey,
		request.SecretRef,
		request.SecretDigest,
		request.ExpectedRecoveryBatchDigest,
		fmt.Sprintf("%d", request.ExpectedRecoveryCodeCount),
	)
	_, _ = mac.Write(recoveryCode)
	return hex.EncodeToString(mac.Sum(nil))
}

func identitySecurityProcessorSecretDigest(
	key []byte,
	accountID string,
	operation string,
	secret []byte,
) string {
	mac := hmac.New(sha256.New, key)
	identitySecurityProcessorWriteCanonical(
		mac,
		"secret",
		accountID,
		operation,
	)
	_, _ = mac.Write(secret)
	return hex.EncodeToString(mac.Sum(nil))
}

func identitySecurityProcessorRecoveryCodeDigest(
	key []byte,
	accountID string,
	code []byte,
) string {
	mac := hmac.New(sha256.New, key)
	identitySecurityProcessorWriteCanonical(mac, "recovery-code", accountID)
	_, _ = mac.Write(code)
	return hex.EncodeToString(mac.Sum(nil))
}

func identitySecurityProcessorRecoveryBatchDigest(
	key []byte,
	accountID string,
	digests []string,
) string {
	canonical := append([]string(nil), digests...)
	sort.Strings(canonical)
	mac := hmac.New(sha256.New, key)
	identitySecurityProcessorWriteCanonical(mac, "recovery-batch", accountID)
	for _, digest := range canonical {
		identitySecurityProcessorWriteCanonical(mac, digest)
	}
	return hex.EncodeToString(mac.Sum(nil))
}

func identitySecurityProcessorHMAC(key []byte, fields ...string) []byte {
	mac := hmac.New(sha256.New, key)
	identitySecurityProcessorWriteCanonical(mac, fields...)
	return mac.Sum(nil)
}

func identitySecurityProcessorWriteCanonical(writer io.Writer, fields ...string) {
	_, _ = io.WriteString(writer, identitySecurityProcessorDigestSchema)
	for _, field := range fields {
		_, _ = writer.Write([]byte{0})
		_, _ = io.WriteString(writer, field)
	}
	_, _ = writer.Write([]byte{0})
}

func identitySecurityProcessorKeyVersions(
	ring IdentitySecurityProcessorKeyRing,
) []string {
	versions := make([]string, 0, len(ring.Keys))
	if _, ok := ring.Keys[ring.ActiveVersion]; ok {
		versions = append(versions, ring.ActiveVersion)
	}
	previous := make([]string, 0, len(ring.Keys)-1)
	for version := range ring.Keys {
		if version != ring.ActiveVersion {
			previous = append(previous, version)
		}
	}
	sort.Strings(previous)
	return append(versions, previous...)
}

func identitySecurityProcessorProvisioningURI(
	issuer string,
	accountID string,
	secret []byte,
) string {
	label := issuer + ":" + accountID
	query := url.Values{}
	query.Set("secret", base32.StdEncoding.WithPadding(base32.NoPadding).EncodeToString(secret))
	query.Set("issuer", issuer)
	query.Set("algorithm", "SHA1")
	query.Set("digits", "6")
	query.Set("period", "30")
	return (&url.URL{
		Scheme:   "otpauth",
		Host:     "totp",
		Path:     "/" + label,
		RawQuery: query.Encode(),
	}).String()
}

func validIdentitySecurityTOTPAt(
	secret []byte,
	code []byte,
	now time.Time,
) bool {
	if len(secret) < 16 || len(secret) > 64 || len(code) != 6 ||
		now.IsZero() {
		return false
	}
	counter := now.Unix() / 30
	for offset := int64(-1); offset <= 1; offset++ {
		expected := identitySecurityTOTPCode(secret, counter+offset)
		if subtle.ConstantTimeCompare(code, expected) == 1 {
			clear(expected)
			return true
		}
		clear(expected)
	}
	return false
}

func identitySecurityTOTPCode(secret []byte, counter int64) []byte {
	message := make([]byte, 8)
	value := uint64(counter)
	for index := len(message) - 1; index >= 0; index-- {
		message[index] = byte(value)
		value >>= 8
	}
	mac := hmac.New(sha1.New, secret)
	_, _ = mac.Write(message)
	digest := mac.Sum(nil)
	clear(message)
	offset := digest[len(digest)-1] & 0x0f
	binaryCode := (uint32(digest[offset])&0x7f)<<24 |
		uint32(digest[offset+1])<<16 |
		uint32(digest[offset+2])<<8 |
		uint32(digest[offset+3])
	clear(digest)
	code := binaryCode % 1_000_000
	return []byte(fmt.Sprintf("%06d", code))
}

func generateIdentitySecurityRecoveryCodes(
	random io.Reader,
	count int,
) ([][]byte, error) {
	const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
	if random == nil || count < 6 || count > 20 {
		return nil, ErrIdentitySecurityProcessorRejected
	}
	codes := make([][]byte, 0, count)
	seen := make(map[string]struct{}, count)
	for len(codes) < count {
		raw := make([]byte, 10)
		randomBytes := make([]byte, len(raw))
		if _, err := io.ReadFull(random, randomBytes); err != nil {
			clear(randomBytes)
			clearIdentitySecurityProcessorByteSlices(codes)
			return nil, ErrIdentitySecurityProcessorUnavailable
		}
		for index := range raw {
			raw[index] = alphabet[int(randomBytes[index])%len(alphabet)]
		}
		clear(randomBytes)
		code := append(append([]byte(nil), raw[:5]...), '-')
		code = append(code, raw[5:]...)
		clear(raw)
		if _, duplicate := seen[string(code)]; duplicate {
			clear(code)
			continue
		}
		seen[string(code)] = struct{}{}
		codes = append(codes, code)
	}
	return codes, nil
}

func clearIdentitySecurityProcessorKeyRing(
	ring *IdentitySecurityProcessorKeyRing,
) {
	if ring == nil {
		return
	}
	for version, key := range ring.Keys {
		clear(key)
		delete(ring.Keys, version)
	}
	ring.ActiveVersion = ""
	ring.Keys = nil
}

func clearIdentitySecurityProcessorRecord(
	record *identitySecurityProcessorRecord,
) {
	if record == nil {
		return
	}
	clear(record.PasswordHash)
	clear(record.TOTPSecret)
	clear(record.PreviousTOTPSecret)
	clearIdentitySecurityProcessorByteSlices(record.RecoveryCodes)
	clearIdentitySecurityProcessorByteSlices(record.PreviousRecoveryCodes)
	*record = identitySecurityProcessorRecord{}
}

func cloneIdentitySecurityProcessorByteSlices(values [][]byte) [][]byte {
	if len(values) == 0 {
		return nil
	}
	cloned := make([][]byte, 0, len(values))
	for _, value := range values {
		cloned = append(cloned, append([]byte(nil), value...))
	}
	return cloned
}

func clearIdentitySecurityProcessorPendingBackup(
	record *identitySecurityProcessorRecord,
) {
	if record == nil {
		return
	}
	record.PreviousConfirmed = false
	clear(record.PreviousTOTPSecret)
	record.PreviousTOTPSecret = nil
	record.PreviousRecoveryVersion = ""
	record.PreviousRecoveryBatch = ""
	record.PreviousRecoveryDigests = nil
	clearIdentitySecurityProcessorByteSlices(record.PreviousRecoveryCodes)
	record.PreviousRecoveryCodes = nil
	record.PreviousHandoffConsumed = false
}

func clearIdentitySecurityProcessorPendingMutation(
	record *identitySecurityProcessorRecord,
) {
	if record == nil {
		return
	}
	record.PendingOperation = ""
	record.PendingIdempotencyKey = ""
	record.PendingRequestDigest = ""
	record.PendingKeyVersion = ""
	record.PendingExpectedBatch = ""
	record.PendingExpectedCount = 0
	record.PendingFinalized = false
	clearIdentitySecurityProcessorPendingBackup(record)
}

func restoreIdentitySecurityProcessorPendingMutation(
	record *identitySecurityProcessorRecord,
) {
	if record == nil {
		return
	}
	record.Confirmed = record.PreviousConfirmed
	clear(record.TOTPSecret)
	record.TOTPSecret = append([]byte(nil), record.PreviousTOTPSecret...)
	record.RecoveryKeyVersion = record.PreviousRecoveryVersion
	record.RecoveryBatchDigest = record.PreviousRecoveryBatch
	record.RecoveryCodeDigests = append(
		[]string(nil),
		record.PreviousRecoveryDigests...,
	)
	clearIdentitySecurityProcessorByteSlices(record.RecoveryCodes)
	record.RecoveryCodes = cloneIdentitySecurityProcessorByteSlices(
		record.PreviousRecoveryCodes,
	)
	record.RecoveryHandoffConsumed = record.PreviousHandoffConsumed
	clearIdentitySecurityProcessorPendingMutation(record)
}

func clearIdentitySecurityProcessorByteSlices(values [][]byte) {
	for _, value := range values {
		clear(value)
	}
}

func clearIdentitySecuritySecretHandoff(handoff *IdentitySecuritySecretHandoff) {
	if handoff == nil {
		return
	}
	handoff.ProvisioningURI = ""
	for index := range handoff.RecoveryCodes {
		handoff.RecoveryCodes[index] = ""
	}
	handoff.RecoveryCodes = nil
}

var (
	_ IdentitySecurityPasswordHasher  = Argon2IdentitySecurityPasswordHasher{}
	_ IdentitySecuritySecretProcessor = (*VaultIdentitySecuritySecretProcessor)(nil)
)
