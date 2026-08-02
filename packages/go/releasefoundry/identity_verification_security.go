package releasefoundry

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
	"sync"
	"time"
)

const IdentityVerificationSecuritySchemaVersion = "releasefoundry.identity_verification_security.v1"

type IdentityVerificationAbuseDimension string

const (
	IdentityVerificationAbuseIdentifier IdentityVerificationAbuseDimension = "identifier"
	IdentityVerificationAbuseAccount    IdentityVerificationAbuseDimension = "account"
	IdentityVerificationAbuseIP         IdentityVerificationAbuseDimension = "ip"
	IdentityVerificationAbuseTenant     IdentityVerificationAbuseDimension = "tenant"
	IdentityVerificationAbuseDevice     IdentityVerificationAbuseDimension = "device"
)

type IdentityVerificationAbuseLimit struct {
	Limit  int
	Window time.Duration
}

type IdentityVerificationAbuseSubject struct {
	Operation        string
	IdentifierDigest string
	AccountID        string
	IPAddress        string
	TenantID         string
	DeviceID         string
}

type IdentityVerificationAbuseDecision struct {
	Allowed             bool
	RetryAfter          time.Duration
	ExhaustedDimensions []IdentityVerificationAbuseDimension
}

type IdentityVerificationAbuseBudget interface {
	CheckAndConsume(context.Context, IdentityVerificationAbuseSubject) (IdentityVerificationAbuseDecision, error)
}

// DatabaseEnforcedIdentityVerificationAbuseBudget delegates the atomic abuse
// decision to the durable challenge-issuance function. It exists so the
// anti-enumeration response policy can remain mandatory without maintaining a
// second, process-local production counter.
type DatabaseEnforcedIdentityVerificationAbuseBudget struct{}

func (DatabaseEnforcedIdentityVerificationAbuseBudget) CheckAndConsume(
	ctx context.Context,
	subject IdentityVerificationAbuseSubject,
) (IdentityVerificationAbuseDecision, error) {
	if err := ctx.Err(); err != nil {
		return IdentityVerificationAbuseDecision{}, err
	}
	if strings.TrimSpace(subject.Operation) == "" {
		return IdentityVerificationAbuseDecision{}, fmt.Errorf("identity verification abuse operation is required")
	}
	return IdentityVerificationAbuseDecision{Allowed: true}, nil
}

type MemoryIdentityVerificationAbuseBudgetOptions struct {
	Now       func() time.Time
	DigestKey []byte
	Limits    map[IdentityVerificationAbuseDimension]IdentityVerificationAbuseLimit
}

type identityVerificationAbuseBucket struct {
	Count     int
	ExpiresAt time.Time
}

// MemoryIdentityVerificationAbuseBudget is a process-local reference
// implementation. Production deployments must use a shared atomic budget.
type MemoryIdentityVerificationAbuseBudget struct {
	mu        sync.Mutex
	now       func() time.Time
	digestKey []byte
	limits    map[IdentityVerificationAbuseDimension]IdentityVerificationAbuseLimit
	buckets   map[string]identityVerificationAbuseBucket
}

func NewMemoryIdentityVerificationAbuseBudget(
	options MemoryIdentityVerificationAbuseBudgetOptions,
) (*MemoryIdentityVerificationAbuseBudget, error) {
	if options.Now == nil {
		options.Now = time.Now
	}
	if len(options.DigestKey) < 32 {
		return nil, fmt.Errorf("identity verification abuse budget digest key must contain at least 32 bytes")
	}
	limits := make(map[IdentityVerificationAbuseDimension]IdentityVerificationAbuseLimit, len(options.Limits))
	for dimension, limit := range options.Limits {
		if !validIdentityVerificationAbuseDimension(dimension) {
			return nil, fmt.Errorf("unsupported identity verification abuse dimension %q", dimension)
		}
		if limit.Limit <= 0 || limit.Window <= 0 {
			return nil, fmt.Errorf("identity verification abuse limit for %s must have a positive limit and window", dimension)
		}
		limits[dimension] = limit
	}
	if len(limits) == 0 {
		return nil, fmt.Errorf("at least one identity verification abuse limit is required")
	}
	return &MemoryIdentityVerificationAbuseBudget{
		now: options.Now, digestKey: append([]byte(nil), options.DigestKey...),
		limits: limits, buckets: make(map[string]identityVerificationAbuseBucket),
	}, nil
}

func (budget *MemoryIdentityVerificationAbuseBudget) CheckAndConsume(
	ctx context.Context,
	subject IdentityVerificationAbuseSubject,
) (IdentityVerificationAbuseDecision, error) {
	if err := ctx.Err(); err != nil {
		return IdentityVerificationAbuseDecision{}, err
	}
	operation := strings.TrimSpace(subject.Operation)
	if operation == "" {
		return IdentityVerificationAbuseDecision{}, fmt.Errorf("identity verification abuse operation is required")
	}

	budget.mu.Lock()
	defer budget.mu.Unlock()
	keys, err := budget.subjectKeys(operation, subject)
	if err != nil {
		return IdentityVerificationAbuseDecision{}, err
	}
	if len(keys) == 0 {
		return IdentityVerificationAbuseDecision{}, fmt.Errorf("identity verification abuse subject has no configured dimensions")
	}

	now := budget.now().UTC()
	decision := IdentityVerificationAbuseDecision{Allowed: true}
	for _, key := range keys {
		bucket := budget.buckets[key.key]
		if !bucket.ExpiresAt.After(now) {
			continue
		}
		if bucket.Count >= key.limit.Limit {
			decision.Allowed = false
			decision.ExhaustedDimensions = append(decision.ExhaustedDimensions, key.dimension)
			if retryAfter := bucket.ExpiresAt.Sub(now); retryAfter > decision.RetryAfter {
				decision.RetryAfter = retryAfter
			}
		}
	}
	if !decision.Allowed {
		return decision, nil
	}
	for _, key := range keys {
		bucket := budget.buckets[key.key]
		if !bucket.ExpiresAt.After(now) {
			bucket = identityVerificationAbuseBucket{ExpiresAt: now.Add(key.limit.Window)}
		}
		bucket.Count++
		budget.buckets[key.key] = bucket
	}
	return decision, nil
}

func (budget *MemoryIdentityVerificationAbuseBudget) Close() {
	budget.mu.Lock()
	defer budget.mu.Unlock()
	for index := range budget.digestKey {
		budget.digestKey[index] = 0
	}
	budget.buckets = make(map[string]identityVerificationAbuseBucket)
}

type identityVerificationAbuseSubjectKey struct {
	dimension IdentityVerificationAbuseDimension
	key       string
	limit     IdentityVerificationAbuseLimit
}

func (budget *MemoryIdentityVerificationAbuseBudget) subjectKeys(
	operation string,
	subject IdentityVerificationAbuseSubject,
) ([]identityVerificationAbuseSubjectKey, error) {
	values := []struct {
		dimension IdentityVerificationAbuseDimension
		value     string
	}{
		{IdentityVerificationAbuseIdentifier, subject.IdentifierDigest},
		{IdentityVerificationAbuseAccount, subject.AccountID},
		{IdentityVerificationAbuseIP, subject.IPAddress},
		{IdentityVerificationAbuseTenant, subject.TenantID},
		{IdentityVerificationAbuseDevice, subject.DeviceID},
	}
	keys := make([]identityVerificationAbuseSubjectKey, 0, len(values))
	for _, candidate := range values {
		limit, configured := budget.limits[candidate.dimension]
		if !configured {
			continue
		}
		value := strings.TrimSpace(candidate.value)
		if value == "" {
			return nil, fmt.Errorf("identity verification abuse subject is missing configured %s dimension", candidate.dimension)
		}
		mac := hmac.New(sha256.New, budget.digestKey)
		_, _ = mac.Write([]byte(operation))
		_, _ = mac.Write([]byte{0})
		_, _ = mac.Write([]byte(candidate.dimension))
		_, _ = mac.Write([]byte{0})
		_, _ = mac.Write([]byte(value))
		keys = append(keys, identityVerificationAbuseSubjectKey{
			dimension: candidate.dimension,
			key:       hex.EncodeToString(mac.Sum(nil)),
			limit:     limit,
		})
	}
	return keys, nil
}

func validIdentityVerificationAbuseDimension(dimension IdentityVerificationAbuseDimension) bool {
	switch dimension {
	case IdentityVerificationAbuseIdentifier,
		IdentityVerificationAbuseAccount,
		IdentityVerificationAbuseIP,
		IdentityVerificationAbuseTenant,
		IdentityVerificationAbuseDevice:
		return true
	default:
		return false
	}
}

type IdentityVerificationPublicResponse struct {
	SchemaVersion string `json:"schema_version"`
	Status        string `json:"status"`
	Message       string `json:"message"`
}

type IdentityVerificationResponsePolicyOptions struct {
	Budget               IdentityVerificationAbuseBudget
	Now                  func() time.Time
	Sleep                func(context.Context, time.Duration) error
	MinimumResponseDelay time.Duration
}

// IdentityVerificationResponsePolicy deliberately returns the same public
// response for successful, rejected, unavailable, and budget-exhausted work.
// Internal outcomes belong in private audit events, never in this envelope.
type IdentityVerificationResponsePolicy struct {
	budget               IdentityVerificationAbuseBudget
	now                  func() time.Time
	sleep                func(context.Context, time.Duration) error
	minimumResponseDelay time.Duration
}

func NewIdentityVerificationResponsePolicy(
	options IdentityVerificationResponsePolicyOptions,
) (*IdentityVerificationResponsePolicy, error) {
	if options.Budget == nil {
		return nil, fmt.Errorf("identity verification abuse budget is required")
	}
	if options.Now == nil {
		options.Now = time.Now
	}
	if options.Sleep == nil {
		options.Sleep = sleepIdentityVerificationResponse
	}
	if options.MinimumResponseDelay < 0 {
		return nil, fmt.Errorf("identity verification minimum response delay must not be negative")
	}
	return &IdentityVerificationResponsePolicy{
		budget: options.Budget, now: options.Now, sleep: options.Sleep,
		minimumResponseDelay: options.MinimumResponseDelay,
	}, nil
}

func (policy *IdentityVerificationResponsePolicy) Execute(
	ctx context.Context,
	startedAt time.Time,
	subject IdentityVerificationAbuseSubject,
	operation func(context.Context) error,
) (IdentityVerificationPublicResponse, error) {
	if operation == nil {
		return IdentityVerificationPublicResponse{}, fmt.Errorf("identity verification protected operation is required")
	}
	decision, budgetErr := policy.budget.CheckAndConsume(ctx, subject)
	if budgetErr == nil && decision.Allowed {
		// The public response intentionally does not depend on this error.
		_ = operation(ctx)
	}
	if err := policy.wait(ctx, startedAt); err != nil {
		return IdentityVerificationPublicResponse{}, err
	}
	return IdentityVerificationPublicResponse{
		SchemaVersion: IdentityVerificationSecuritySchemaVersion,
		Status:        "accepted",
		Message:       "If the request is eligible, verification instructions will be sent.",
	}, nil
}

func (policy *IdentityVerificationResponsePolicy) wait(ctx context.Context, startedAt time.Time) error {
	if policy.minimumResponseDelay == 0 {
		return ctx.Err()
	}
	elapsed := policy.now().UTC().Sub(startedAt.UTC())
	remaining := policy.minimumResponseDelay - elapsed
	if remaining <= 0 {
		return ctx.Err()
	}
	return policy.sleep(ctx, remaining)
}

func sleepIdentityVerificationResponse(ctx context.Context, duration time.Duration) error {
	timer := time.NewTimer(duration)
	defer timer.Stop()
	select {
	case <-timer.C:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

var _ IdentityVerificationAbuseBudget = (*MemoryIdentityVerificationAbuseBudget)(nil)
