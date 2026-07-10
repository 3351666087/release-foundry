package main

import (
	"context"
	"strings"
	"testing"

	"github.com/ashr-labs/ashr/packages/go/ashrclone"
)

func lookup(values map[string]string) func(string) (string, bool) {
	return func(key string) (string, bool) {
		value, ok := values[key]
		return value, ok
	}
}

func TestIdentityRuntimeDefaultsToPostgresAndFailsClosedWithoutDSN(t *testing.T) {
	_, err := newIdentityRuntimeFromEnv(context.Background(), lookup(map[string]string{}))
	if err == nil || !strings.Contains(err.Error(), "ASHR_POSTGRES_DSN") {
		t.Fatalf("expected missing postgres DSN error, got %v", err)
	}
}

func TestIdentityRuntimeMemoryRequiresExplicitDevelopmentOptIn(t *testing.T) {
	for _, values := range []map[string]string{
		{"ASHR_IDENTITY_RUNTIME": "memory"},
		{"ASHR_IDENTITY_RUNTIME": "memory", "ASHR_ENVIRONMENT": "production", "ASHR_IDENTITY_MEMORY_ENABLED": "true"},
		{"ASHR_IDENTITY_RUNTIME": "memory", "ASHR_ENVIRONMENT": "development"},
	} {
		if _, err := newIdentityRuntimeFromEnv(context.Background(), lookup(values)); err == nil {
			t.Fatalf("expected memory configuration to fail: %#v", values)
		}
	}
	runtime, err := newIdentityRuntimeFromEnv(context.Background(), lookup(map[string]string{
		"ASHR_IDENTITY_RUNTIME":        "memory",
		"ASHR_ENVIRONMENT":             "development",
		"ASHR_IDENTITY_MEMORY_ENABLED": "true",
	}))
	if err != nil {
		t.Fatal(err)
	}
	if runtime.mode != ashrclone.IdentityRuntimeMemory || runtime.unifiedIdentity == nil {
		t.Fatalf("unexpected memory runtime: %#v", runtime)
	}
}

func TestIdentityRuntimeRejectsUnknownMode(t *testing.T) {
	_, err := newIdentityRuntimeFromEnv(context.Background(), lookup(map[string]string{
		"ASHR_IDENTITY_RUNTIME": "automatic",
	}))
	if err == nil || !strings.Contains(err.Error(), "unsupported") {
		t.Fatalf("expected unsupported mode error, got %v", err)
	}
}
