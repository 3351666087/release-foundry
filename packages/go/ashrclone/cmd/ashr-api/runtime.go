package main

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/ashr-labs/ashr/packages/go/ashrclone"
)

type identityRuntime struct {
	mode                       string
	unifiedIdentity            *ashrclone.UnifiedIdentityService
	identitySessions           ashrclone.IdentityHTTPSessionResolver
	postgres                   *ashrclone.ProductionIdentityStore
	outbox                     ashrclone.OAuthRevocationOutboxStore
	verification               *ashrclone.IdentityVerificationService
	verificationResponsePolicy *ashrclone.IdentityVerificationResponsePolicy
	close                      func() error
}

func newIdentityRuntimeFromEnv(ctx context.Context, lookup func(string) (string, bool)) (identityRuntime, error) {
	if lookup == nil {
		return identityRuntime{}, fmt.Errorf("identity environment lookup is required")
	}
	environment := strings.ToLower(env(lookup, "ASHR_ENVIRONMENT"))
	if environment == "" {
		environment = "production"
	}
	mode := strings.ToLower(env(lookup, "ASHR_IDENTITY_RUNTIME"))
	if mode == "" {
		mode = ashrclone.IdentityRuntimePostgres
	}
	switch mode {
	case ashrclone.IdentityRuntimeMemory:
		return newDevelopmentIdentityRuntime(environment, mode, lookup)
	case ashrclone.IdentityRuntimePostgres:
		dsn := firstEnv(lookup, "ASHR_POSTGRES_DSN", "DATABASE_URL")
		sessionKey := envRaw(lookup, "ASHR_IDENTITY_SESSION_HMAC_KEY")
		store, err := ashrclone.OpenProductionIdentityStore(dsn, []byte(sessionKey))
		if err != nil {
			return identityRuntime{}, err
		}
		readyCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
		defer cancel()
		if err := store.Ready(readyCtx); err != nil {
			_ = store.Close()
			return identityRuntime{}, err
		}
		outbox, err := store.NewOAuthRevocationOutboxStore()
		if err != nil {
			_ = store.Close()
			return identityRuntime{}, err
		}
		if envTrue(lookup, "ASHR_GITHUB_OAUTH_ENABLED") || envTrue(lookup, "ASHR_GOOGLE_OAUTH_ENABLED") {
			_ = store.Close()
			return identityRuntime{}, fmt.Errorf("production OAuth requires an injected external opaque vault; refusing memory or plaintext token storage")
		}
		runtime := identityRuntime{
			mode:             mode,
			identitySessions: store,
			postgres:         store,
			outbox:           outbox,
			close:            store.Close,
		}
		if envTrue(lookup, "ASHR_IDENTITY_VERIFICATION_ENABLED") {
			digestKey := envRaw(lookup, "ASHR_IDENTITY_VERIFICATION_HMAC_KEY")
			verificationStore, verificationErr := store.NewIdentityVerificationStore(
				ashrclone.PostgresIdentityVerificationStoreOptions{
					OrganizationID: env(lookup, "ASHR_IDENTITY_VERIFICATION_ORGANIZATION_ID"),
					ProjectID:      env(lookup, "ASHR_IDENTITY_VERIFICATION_PROJECT_ID"),
					PrincipalID:    env(lookup, "ASHR_IDENTITY_VERIFICATION_PRINCIPAL_ID"),
					DigestKey:      []byte(digestKey),
				},
			)
			if verificationErr != nil {
				_ = store.Close()
				return identityRuntime{}, fmt.Errorf("configure production identity verification store: %w", verificationErr)
			}
			var coordinator *ashrclone.PostgresIdentityVerificationTransactionCoordinator
			coordinator, coordinatorErr := store.NewIdentityVerificationTransactionCoordinator(verificationStore)
			if coordinatorErr != nil {
				verificationStore.Close()
				_ = store.Close()
				return identityRuntime{}, fmt.Errorf("configure production identity verification transaction coordinator: %w", coordinatorErr)
			}
			sender, senderErr := productionIdentityVerificationSenderFromEnv(lookup)
			if senderErr != nil {
				verificationStore.Close()
				_ = store.Close()
				return identityRuntime{}, senderErr
			}
			verification, verificationErr := ashrclone.NewIdentityVerificationService(
				ashrclone.IdentityVerificationServiceOptions{
					Store: verificationStore, Sender: sender,
					TransactionCoordinator: coordinator, DigestKey: []byte(digestKey),
				},
			)
			if verificationErr != nil {
				verificationStore.Close()
				_ = store.Close()
				return identityRuntime{}, fmt.Errorf("configure production identity verification service: %w", verificationErr)
			}
			responsePolicy, policyErr := ashrclone.NewIdentityVerificationResponsePolicy(
				ashrclone.IdentityVerificationResponsePolicyOptions{
					Budget: ashrclone.DatabaseEnforcedIdentityVerificationAbuseBudget{},
				},
			)
			if policyErr != nil {
				verification.Close()
				verificationStore.Close()
				_ = store.Close()
				return identityRuntime{}, fmt.Errorf("configure production identity verification response policy: %w", policyErr)
			}
			runtime.verification = verification
			runtime.verificationResponsePolicy = responsePolicy
			runtime.close = func() error {
				verification.Close()
				verificationStore.Close()
				return store.Close()
			}
		}
		return runtime, nil
	default:
		return identityRuntime{}, fmt.Errorf("unsupported ASHR_IDENTITY_RUNTIME %q", mode)
	}
}

func productionIdentityVerificationSenderFromEnv(
	lookup func(string) (string, bool),
) (ashrclone.IdentityVerificationSender, error) {
	if !envTrue(lookup, "ASHR_IDENTITY_VERIFICATION_SMTP_ENABLED") {
		return nil, fmt.Errorf("production identity verification requires ASHR_IDENTITY_VERIFICATION_SMTP_ENABLED=true")
	}
	return developmentIdentityVerificationSenderFromEnv(lookup)
}

func developmentIdentityVerificationSenderFromEnv(
	lookup func(string) (string, bool),
) (ashrclone.IdentityVerificationSender, error) {
	if !envTrue(lookup, "ASHR_IDENTITY_VERIFICATION_SMTP_ENABLED") {
		return &ashrclone.MemoryIdentityVerificationSender{}, nil
	}
	host := env(lookup, "ASHR_SMTP_HOST")
	portValue := env(lookup, "ASHR_SMTP_PORT")
	from := env(lookup, "ASHR_SMTP_FROM")
	authCode := envRaw(lookup, "ASHR_SMTP_AUTH_CODE")
	missing := make([]string, 0, 4)
	if host == "" {
		missing = append(missing, "ASHR_SMTP_HOST")
	}
	if portValue == "" {
		missing = append(missing, "ASHR_SMTP_PORT")
	}
	if from == "" {
		missing = append(missing, "ASHR_SMTP_FROM")
	}
	if strings.TrimSpace(authCode) == "" {
		missing = append(missing, "ASHR_SMTP_AUTH_CODE")
	}
	if len(missing) != 0 {
		return nil, fmt.Errorf("development identity verification SMTP requires complete configuration: %s", strings.Join(missing, ", "))
	}
	port, err := strconv.Atoi(portValue)
	if err != nil || port < 1 || port > 65535 {
		return nil, fmt.Errorf("development identity verification SMTP requires a valid ASHR_SMTP_PORT")
	}
	sender, err := ashrclone.NewSMTPIdentityVerificationSender(ashrclone.SMTPIdentityVerificationSenderOptions{
		Host: host, Port: port, From: from, AuthCode: authCode,
	})
	if err != nil {
		return nil, fmt.Errorf("configure development identity verification SMTP sender: invalid SMTP configuration")
	}
	return sender, nil
}

func env(lookup func(string) (string, bool), key string) string {
	value, _ := lookup(key)
	return strings.TrimSpace(value)
}

func envRaw(lookup func(string) (string, bool), key string) string {
	value, _ := lookup(key)
	return value
}

func envTrue(lookup func(string) (string, bool), key string) bool {
	value, ok := lookup(key)
	if !ok {
		return false
	}
	parsed, err := strconv.ParseBool(strings.TrimSpace(value))
	return err == nil && parsed
}

func firstEnv(lookup func(string) (string, bool), keys ...string) string {
	for _, key := range keys {
		if value := env(lookup, key); value != "" {
			return value
		}
	}
	return ""
}

func productionIdentityRuntime(ctx context.Context) (identityRuntime, error) {
	return newIdentityRuntimeFromEnv(ctx, os.LookupEnv)
}
