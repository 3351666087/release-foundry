package releasefoundry

import (
	"context"
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
	Backend               ControlPlaneBackend
	ProviderDispatch      ProviderDispatchBackend
	PaymentReconciliation *PaymentReconciliationService
	PaymentDomain         *PaymentDomainService
	Name                  string
	Ready                 bool
	Close                 func() error
	Migrate               func(context.Context) error
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
		reconciliation, err := NewPaymentReconciliationService(NewMemoryPaymentReconciliationRepository())
		if err != nil {
			return BackendSelection{}, err
		}
		payments, err := NewPaymentDomainService(NewMemoryPaymentDomainRepository())
		if err != nil {
			return BackendSelection{}, err
		}
		return BackendSelection{Backend: NewMemoryService(), PaymentReconciliation: reconciliation, PaymentDomain: payments, Name: "memory_service_v0", Ready: true}, nil
	case BackendKindPostgres:
		dsn := strings.TrimSpace(config.PostgresDSN)
		if dsn == "" {
			return BackendSelection{}, fmt.Errorf("postgres backend requires RELEASEFOUNDRY_POSTGRES_DSN or DATABASE_URL")
		}
		repository, err := OpenPostgresRepository(dsn)
		if err != nil {
			return BackendSelection{}, err
		}
		reconciliation, err := NewPaymentReconciliationService(repository)
		if err != nil {
			_ = repository.Close()
			return BackendSelection{}, err
		}
		payments, err := NewPaymentDomainService(repository)
		if err != nil {
			_ = repository.Close()
			return BackendSelection{}, err
		}
		migrate := func(ctx context.Context) error {
			if err := repository.Migrate(ctx); err != nil {
				return err
			}
			if err := repository.MigratePaymentReconciliation(ctx); err != nil {
				return err
			}
			return repository.MigratePaymentDomain(ctx)
		}
		return BackendSelection{Backend: repository, ProviderDispatch: repository, PaymentReconciliation: reconciliation, PaymentDomain: payments, Name: "postgres_repository_v0", Close: repository.Close, Migrate: migrate}, nil
	default:
		return BackendSelection{}, fmt.Errorf("unsupported backend %q", config.Kind)
	}
}

func backendConfigFromLookup(lookup func(string) (string, bool)) BackendConfig {
	kind := firstLookup(lookup, "RELEASEFOUNDRY_GO_BACKEND", "RELEASEFOUNDRY_BACKEND")
	dsn := firstLookup(lookup, "RELEASEFOUNDRY_POSTGRES_DSN", "DATABASE_URL")
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
