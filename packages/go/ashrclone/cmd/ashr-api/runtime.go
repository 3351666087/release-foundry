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
	mode             string
	unifiedIdentity  *ashrclone.UnifiedIdentityService
	identitySessions ashrclone.IdentityHTTPSessionResolver
	postgres         *ashrclone.ProductionIdentityStore
	outbox           ashrclone.OAuthRevocationOutboxStore
	close            func() error
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
		if environment != "development" || !envTrue(lookup, "ASHR_IDENTITY_MEMORY_ENABLED") {
			return identityRuntime{}, fmt.Errorf("memory identity runtime requires ASHR_ENVIRONMENT=development and ASHR_IDENTITY_MEMORY_ENABLED=true")
		}
		identity, err := ashrclone.NewUnifiedIdentityService(ashrclone.UnifiedIdentityServiceOptions{})
		if err != nil {
			return identityRuntime{}, fmt.Errorf("configure development identity memory: %w", err)
		}
		return identityRuntime{mode: mode, unifiedIdentity: identity}, nil
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
		return identityRuntime{
			mode:             mode,
			identitySessions: store,
			postgres:         store,
			outbox:           outbox,
			close:            store.Close,
		}, nil
	default:
		return identityRuntime{}, fmt.Errorf("unsupported ASHR_IDENTITY_RUNTIME %q", mode)
	}
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
