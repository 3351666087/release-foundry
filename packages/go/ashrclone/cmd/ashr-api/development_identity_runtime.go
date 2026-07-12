package main

import (
	"fmt"
	"time"

	"github.com/ashr-labs/ashr/packages/go/ashrclone"
)

func newDevelopmentIdentityRuntime(
	environment string,
	mode string,
	lookup func(string) (string, bool),
) (identityRuntime, error) {
	if environment != "development" || !envTrue(lookup, "ASHR_IDENTITY_MEMORY_ENABLED") {
		return identityRuntime{}, fmt.Errorf("memory identity runtime requires ASHR_ENVIRONMENT=development and ASHR_IDENTITY_MEMORY_ENABLED=true")
	}
	identity, err := ashrclone.NewUnifiedIdentityService(ashrclone.UnifiedIdentityServiceOptions{})
	if err != nil {
		return identityRuntime{}, fmt.Errorf("configure development identity memory: %w", err)
	}
	lifecycle, err := ashrclone.NewIdentityLifecycleService(identity, ashrclone.IdentityLifecycleOptions{
		GitHubEnabled: envTrue(lookup, "ASHR_GITHUB_OAUTH_ENABLED"),
		GoogleEnabled: envTrue(lookup, "ASHR_GOOGLE_OAUTH_ENABLED"),
		Environment:   environment,
	})
	if err != nil {
		return identityRuntime{}, fmt.Errorf("configure development identity lifecycle: %w", err)
	}
	runtime := identityRuntime{mode: mode, unifiedIdentity: identity, identityLifecycle: lifecycle}
	if !envTrue(lookup, "ASHR_IDENTITY_VERIFICATION_ENABLED") {
		return runtime, nil
	}
	if !envTrue(lookup, "ASHR_IDENTITY_VERIFICATION_MEMORY_ENABLED") {
		return identityRuntime{}, fmt.Errorf("development identity verification requires ASHR_IDENTITY_VERIFICATION_MEMORY_ENABLED=true")
	}
	digestKey := envRaw(lookup, "ASHR_IDENTITY_VERIFICATION_HMAC_KEY")
	sender, senderErr := developmentIdentityVerificationSenderFromEnv(lookup)
	if senderErr != nil {
		return identityRuntime{}, senderErr
	}
	verification, verificationErr := ashrclone.NewIdentityVerificationService(
		ashrclone.IdentityVerificationServiceOptions{
			Store:     ashrclone.NewMemoryIdentityVerificationStore(time.Now),
			Sender:    sender,
			Identity:  identity,
			DigestKey: []byte(digestKey),
		},
	)
	if verificationErr != nil {
		return identityRuntime{}, fmt.Errorf("configure development identity verification: %w", verificationErr)
	}
	budget, budgetErr := ashrclone.NewMemoryIdentityVerificationAbuseBudget(
		ashrclone.MemoryIdentityVerificationAbuseBudgetOptions{
			DigestKey: []byte(digestKey),
			Limits: map[ashrclone.IdentityVerificationAbuseDimension]ashrclone.IdentityVerificationAbuseLimit{
				ashrclone.IdentityVerificationAbuseIdentifier: {Limit: 5, Window: time.Hour},
				ashrclone.IdentityVerificationAbuseIP:         {Limit: 20, Window: time.Hour},
				ashrclone.IdentityVerificationAbuseTenant:     {Limit: 50, Window: time.Hour},
			},
		},
	)
	if budgetErr != nil {
		verification.Close()
		return identityRuntime{}, fmt.Errorf("configure development identity verification abuse budget: %w", budgetErr)
	}
	responsePolicy, policyErr := ashrclone.NewIdentityVerificationResponsePolicy(
		ashrclone.IdentityVerificationResponsePolicyOptions{Budget: budget},
	)
	if policyErr != nil {
		budget.Close()
		verification.Close()
		return identityRuntime{}, fmt.Errorf("configure development identity verification response policy: %w", policyErr)
	}
	runtime.verification = verification
	runtime.verificationResponsePolicy = responsePolicy
	runtime.close = func() error {
		budget.Close()
		verification.Close()
		return nil
	}
	return runtime, nil
}
