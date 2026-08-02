package releasefoundry

import (
	"strings"
	"testing"
)

func TestNewBackendDefaultsToMemory(t *testing.T) {
	selection, err := NewBackend(BackendConfig{})
	if err != nil {
		t.Fatal(err)
	}
	if selection.Name != "memory_service_v0" {
		t.Fatalf("backend name = %q", selection.Name)
	}
	if _, ok := selection.Backend.(*MemoryService); !ok {
		t.Fatalf("backend type = %T", selection.Backend)
	}
	if selection.Close != nil {
		t.Fatalf("memory backend should not require close")
	}
}

func TestBackendConfigFromEnvLookup(t *testing.T) {
	lookup := func(key string) (string, bool) {
		values := map[string]string{
			"RELEASEFOUNDRY_GO_BACKEND":   "postgres",
			"RELEASEFOUNDRY_POSTGRES_DSN": "postgres://example.test/releasefoundry?sslmode=disable",
		}
		value, ok := values[key]
		return value, ok
	}
	config := backendConfigFromLookup(lookup)
	if config.Kind != "postgres" {
		t.Fatalf("kind = %q", config.Kind)
	}
	if config.PostgresDSN == "" {
		t.Fatalf("expected postgres DSN from env lookup")
	}
}

func TestNewBackendPostgresExposesMigrationHook(t *testing.T) {
	selection, err := NewBackend(BackendConfig{Kind: "postgres", PostgresDSN: "postgres://example.test/releasefoundry?sslmode=disable"})
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if selection.Close != nil {
			_ = selection.Close()
		}
	}()
	if selection.Name != "postgres_repository_v0" {
		t.Fatalf("backend name = %q", selection.Name)
	}
	if selection.Ready {
		t.Fatalf("postgres backend should not be ready before migration")
	}
	if selection.Migrate == nil {
		t.Fatalf("postgres backend should expose migration hook")
	}
}
func TestNewBackendPostgresRequiresDSN(t *testing.T) {
	_, err := NewBackend(BackendConfig{Kind: "postgres"})
	if err == nil {
		t.Fatal("expected missing DSN error")
	}
	message := err.Error()
	if !strings.Contains(message, "RELEASEFOUNDRY_POSTGRES_DSN") || strings.Contains(message, "postgres://") {
		t.Fatalf("unexpected error message: %q", message)
	}
}

func TestNewBackendRejectsUnsupportedKind(t *testing.T) {
	_, err := NewBackend(BackendConfig{Kind: "sqlite"})
	if err == nil || !strings.Contains(err.Error(), "unsupported backend") {
		t.Fatalf("expected unsupported backend error, got %v", err)
	}
}
