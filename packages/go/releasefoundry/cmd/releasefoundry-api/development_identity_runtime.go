package main

import (
	"fmt"
	"time"

	"github.com/3351666087/release-foundry/packages/go/releasefoundry"
)

func newDevelopmentIdentityRuntime(
	environment string,
	mode string,
	lookup func(string) (string, bool),
) (identityRuntime, error) {
	if environment != "development" || !envTrue(lookup, "RELEASEFOUNDRY_IDENTITY_MEMORY_ENABLED") {
		return identityRuntime{}, fmt.Errorf("memory identity runtime requires RELEASEFOUNDRY_ENVIRONMENT=development and RELEASEFOUNDRY_IDENTITY_MEMORY_ENABLED=true")
	}
	identity, err := releasefoundry.NewUnifiedIdentityService(releasefoundry.UnifiedIdentityServiceOptions{})
	if err != nil {
		return identityRuntime{}, fmt.Errorf("configure development identity memory: %w", err)
	}
	lifecycle, err := releasefoundry.NewIdentityLifecycleService(identity, releasefoundry.IdentityLifecycleOptions{
		GitHubEnabled: envTrue(lookup, "RELEASEFOUNDRY_GITHUB_OAUTH_ENABLED"),
		GoogleEnabled: envTrue(lookup, "RELEASEFOUNDRY_GOOGLE_OAUTH_ENABLED"),
		Environment:   environment,
	})
	if err != nil {
		return identityRuntime{}, fmt.Errorf("configure development identity lifecycle: %w", err)
	}
	runtime := identityRuntime{mode: mode, unifiedIdentity: identity, identityLifecycle: lifecycle}
	if !envTrue(lookup, "RELEASEFOUNDRY_IDENTITY_VERIFICATION_ENABLED") {
		return runtime, nil
	}
	if !envTrue(lookup, "RELEASEFOUNDRY_IDENTITY_VERIFICATION_MEMORY_ENABLED") {
		return identityRuntime{}, fmt.Errorf("development identity verification requires RELEASEFOUNDRY_IDENTITY_VERIFICATION_MEMORY_ENABLED=true")
	}
	digestKey := envRaw(lookup, "RELEASEFOUNDRY_IDENTITY_VERIFICATION_HMAC_KEY")
	sender, senderErr := developmentIdentityVerificationSenderFromEnv(lookup)
	if senderErr != nil {
		return identityRuntime{}, senderErr
	}
	verification, verificationErr := releasefoundry.NewIdentityVerificationService(
		releasefoundry.IdentityVerificationServiceOptions{
			Store:     releasefoundry.NewMemoryIdentityVerificationStore(time.Now),
			Sender:    sender,
			Identity:  identity,
			DigestKey: []byte(digestKey),
		},
	)
	if verificationErr != nil {
		return identityRuntime{}, fmt.Errorf("configure development identity verification: %w", verificationErr)
	}
	budget, budgetErr := releasefoundry.NewMemoryIdentityVerificationAbuseBudget(
		releasefoundry.MemoryIdentityVerificationAbuseBudgetOptions{
			DigestKey: []byte(digestKey),
			Limits: map[releasefoundry.IdentityVerificationAbuseDimension]releasefoundry.IdentityVerificationAbuseLimit{
				releasefoundry.IdentityVerificationAbuseIdentifier: {Limit: 5, Window: time.Hour},
				releasefoundry.IdentityVerificationAbuseIP:         {Limit: 20, Window: time.Hour},
				releasefoundry.IdentityVerificationAbuseTenant:     {Limit: 50, Window: time.Hour},
			},
		},
	)
	if budgetErr != nil {
		verification.Close()
		return identityRuntime{}, fmt.Errorf("configure development identity verification abuse budget: %w", budgetErr)
	}
	responsePolicy, policyErr := releasefoundry.NewIdentityVerificationResponsePolicy(
		releasefoundry.IdentityVerificationResponsePolicyOptions{Budget: budget},
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
