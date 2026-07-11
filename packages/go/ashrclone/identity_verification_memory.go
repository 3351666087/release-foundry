package ashrclone

import (
	"context"
	"fmt"
	"sync"
	"time"
)

// MemoryIdentityVerificationStore is development-only. Production must inject
// a durable, cross-instance store with an atomic consume operation.
type MemoryIdentityVerificationStore struct {
	mu         sync.Mutex
	now        func() time.Time
	challenges map[string]IdentityVerificationChallenge
	cooldowns  map[string]time.Time
}

func NewMemoryIdentityVerificationStore(now func() time.Time) *MemoryIdentityVerificationStore {
	if now == nil {
		now = time.Now
	}
	return &MemoryIdentityVerificationStore{
		now: now, challenges: make(map[string]IdentityVerificationChallenge),
		cooldowns: make(map[string]time.Time),
	}
}

func (store *MemoryIdentityVerificationStore) CreateIdentityVerificationChallenge(
	_ context.Context,
	challenge IdentityVerificationChallenge,
	resendCooldown time.Duration,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	now := store.now().UTC()
	key := challengeCooldownKey(challenge)
	if availableAt, ok := store.cooldowns[key]; ok && availableAt.After(now) {
		return IdentityVerificationError{Code: "verification_resend_cooldown", Message: "verification resend cooldown is active"}
	}
	if _, exists := store.challenges[challenge.ChallengeID]; exists {
		return fmt.Errorf("identity verification challenge id already exists")
	}
	store.challenges[challenge.ChallengeID] = cloneVerificationChallenge(challenge)
	store.cooldowns[key] = now.Add(resendCooldown)
	return nil
}

func (store *MemoryIdentityVerificationStore) ConsumeIdentityVerificationChallenge(
	_ context.Context,
	challengeID string,
	verify func(IdentityVerificationChallenge) error,
) (IdentityVerificationChallenge, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	challenge, ok := store.challenges[challengeID]
	if !ok {
		return IdentityVerificationChallenge{}, ErrIdentityVerificationNotFound
	}
	now := store.now().UTC()
	if challenge.ConsumedAt != nil {
		return IdentityVerificationChallenge{}, ErrIdentityVerificationConsumed
	}
	if !challenge.ExpiresAt.After(now) {
		consumed := now
		challenge.ConsumedAt = &consumed
		store.challenges[challengeID] = challenge
		return IdentityVerificationChallenge{}, IdentityVerificationError{Code: "verification_expired", Message: "verification challenge expired"}
	}
	if challenge.AttemptCount >= challenge.AttemptCap {
		return IdentityVerificationChallenge{}, IdentityVerificationError{Code: "verification_attempts_exhausted", Message: "verification attempt limit reached"}
	}
	if err := verify(cloneVerificationChallenge(challenge)); err != nil {
		challenge.AttemptCount++
		if challenge.AttemptCount >= challenge.AttemptCap {
			consumed := now
			challenge.ConsumedAt = &consumed
		}
		store.challenges[challengeID] = challenge
		return IdentityVerificationChallenge{}, err
	}
	challenge.AttemptCount++
	consumed := now
	challenge.ConsumedAt = &consumed
	store.challenges[challengeID] = challenge
	return cloneVerificationChallenge(challenge), nil
}

func challengeCooldownKey(challenge IdentityVerificationChallenge) string {
	return string(challenge.Channel) + "\x00" + challenge.IdentifierDigest + "\x00" +
		string(challenge.Purpose) + "\x00" + challenge.TenantID + "\x00" + challenge.AccountID
}

func cloneVerificationChallenge(challenge IdentityVerificationChallenge) IdentityVerificationChallenge {
	if challenge.ConsumedAt != nil {
		value := *challenge.ConsumedAt
		challenge.ConsumedAt = &value
	}
	return challenge
}

type MemoryIdentityVerificationSender struct {
	mu         sync.Mutex
	deliveries []IdentityVerificationDelivery
	err        error
}

func (sender *MemoryIdentityVerificationSender) SendIdentityVerification(
	_ context.Context,
	delivery IdentityVerificationDelivery,
) error {
	sender.mu.Lock()
	defer sender.mu.Unlock()
	if sender.err != nil {
		return sender.err
	}
	sender.deliveries = append(sender.deliveries, delivery)
	return nil
}

func (sender *MemoryIdentityVerificationSender) Deliveries() []IdentityVerificationDelivery {
	sender.mu.Lock()
	defer sender.mu.Unlock()
	return append([]IdentityVerificationDelivery(nil), sender.deliveries...)
}

func (sender *MemoryIdentityVerificationSender) SetError(err error) {
	sender.mu.Lock()
	sender.err = err
	sender.mu.Unlock()
}

var (
	_ IdentityVerificationStore  = (*MemoryIdentityVerificationStore)(nil)
	_ IdentityVerificationSender = (*MemoryIdentityVerificationSender)(nil)
)
