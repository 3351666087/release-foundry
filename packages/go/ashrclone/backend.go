package ashrclone

import (
	"fmt"
	"os"
	"strings"
)

const (
	BackendKindMemory   = "memory"
	BackendKindPostgres = "postgres"
)

type BackendConfig struct {
	Kind        string
	PostgresDSN string
}

type BackendSelection struct {
	Backend ControlPlaneBackend
	Name    string
	Close   func() error
}

func BackendConfigFromEnv() BackendConfig {
	return backendConfigFromLookup(os.LookupEnv)
}

func NewBackendFromEnv() (BackendSelection, error) {
	return NewBackend(BackendConfigFromEnv())
}

func NewBackend(config BackendConfig) (BackendSelection, error) {
	kind := normalizeBackendKind(config.Kind)
	switch kind {
	case BackendKindMemory:
		return BackendSelection{Backend: NewMemoryService(), Name: "memory_service_v0"}, nil
	case BackendKindPostgres:
		dsn := strings.TrimSpace(config.PostgresDSN)
		if dsn == "" {
			return BackendSelection{}, fmt.Errorf("postgres backend requires ASHR_POSTGRES_DSN or DATABASE_URL")
		}
		repository, err := OpenPostgresRepository(dsn)
		if err != nil {
			return BackendSelection{}, err
		}
		return BackendSelection{Backend: repository, Name: "postgres_repository_v0", Close: repository.Close}, nil
	default:
		return BackendSelection{}, fmt.Errorf("unsupported backend %q", config.Kind)
	}
}

func backendConfigFromLookup(lookup func(string) (string, bool)) BackendConfig {
	kind := firstLookup(lookup, "ASHR_GO_BACKEND", "ASHR_BACKEND")
	dsn := firstLookup(lookup, "ASHR_POSTGRES_DSN", "DATABASE_URL")
	return BackendConfig{Kind: kind, PostgresDSN: dsn}
}

func normalizeBackendKind(kind string) string {
	switch strings.ToLower(strings.TrimSpace(kind)) {
	case "", "memory", "mem", "inmemory", "memory_service_v0":
		return BackendKindMemory
	case "postgres", "postgresql", "pg", "postgres_repository_v0":
		return BackendKindPostgres
	default:
		return strings.ToLower(strings.TrimSpace(kind))
	}
}

func firstLookup(lookup func(string) (string, bool), keys ...string) string {
	for _, key := range keys {
		value, ok := lookup(key)
		if ok && strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}
