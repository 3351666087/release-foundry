package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/3351666087/release-foundry/packages/go/releasefoundry"
)

const (
	identityDeliveryTestTenantID  = "11111111-1111-4111-8111-111111111111"
	identityDeliveryTestProjectID = "22222222-2222-4222-8222-222222222222"
)

type identityDeliveryTestRunner struct {
	run func(
		context.Context,
		releasefoundry.IdentityDeliveryDaemonOptions,
	) (releasefoundry.IdentityDeliveryRunResult, error)
}

func (runner identityDeliveryTestRunner) Run(
	ctx context.Context,
	options releasefoundry.IdentityDeliveryDaemonOptions,
) (releasefoundry.IdentityDeliveryRunResult, error) {
	return runner.run(ctx, options)
}

func TestIdentityDeliveryCommandConfigDefaults(t *testing.T) {
	environment := identityDeliveryTestEnvironment()
	config, err := identityDeliveryCommandConfigFromEnv(
		identityDeliveryMapLookup(environment),
	)
	if err != nil {
		t.Fatal(err)
	}
	if config.batchSize != 50 || config.maxOpenConnections != 8 ||
		config.maxAttempts != 8 || config.pollInterval != time.Second ||
		config.shutdownTimeout != 20*time.Second ||
		config.healthAddress != "127.0.0.1:8081" ||
		config.mtlsProfileMode != identityDeliveryMTLSProfileModeSeparate ||
		config.vaultMTLS.serverName != "vault.internal" ||
		config.relayMTLS.serverName != "relay.internal" {
		t.Fatalf("unexpected defaults: %#v", config)
	}
}

func TestIdentityDeliveryCommandConfigAllowsDeliberateSharedMTLSProfile(t *testing.T) {
	environment := identityDeliveryTestEnvironment()
	environment["RELEASEFOUNDRY_IDENTITY_DELIVERY_MTLS_PROFILE_MODE"] = "shared"
	for _, key := range []string{
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_CA_FILE",
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_CERT_FILE",
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_KEY_FILE",
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_RELAY_MTLS_CA_FILE",
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_RELAY_MTLS_CLIENT_CERT_FILE",
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_RELAY_MTLS_CLIENT_KEY_FILE",
	} {
		delete(environment, key)
	}
	environment["RELEASEFOUNDRY_IDENTITY_DELIVERY_SHARED_MTLS_CA_FILE"] = "/run/secrets/shared-ca.pem"
	environment["RELEASEFOUNDRY_IDENTITY_DELIVERY_SHARED_MTLS_CLIENT_CERT_FILE"] = "/run/secrets/shared-cert.pem"
	environment["RELEASEFOUNDRY_IDENTITY_DELIVERY_SHARED_MTLS_CLIENT_KEY_FILE"] = "/run/secrets/shared-key.pem"
	config, err := identityDeliveryCommandConfigFromEnv(identityDeliveryMapLookup(environment))
	if err != nil {
		t.Fatal(err)
	}
	if config.vaultMTLS.caBundleFile != config.relayMTLS.caBundleFile ||
		config.vaultMTLS.clientCertificateFile != config.relayMTLS.clientCertificateFile ||
		config.vaultMTLS.clientPrivateKeyFile != config.relayMTLS.clientPrivateKeyFile {
		t.Fatal("explicit shared profile did not share all workload identity material")
	}
}

func TestIdentityDeliveryCommandConfigFailsClosed(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(map[string]string)
		want   string
	}{
		{
			name: "explicit blank optional",
			mutate: func(environment map[string]string) {
				environment["RELEASEFOUNDRY_IDENTITY_DELIVERY_BATCH_SIZE"] = " "
			},
			want: "must not be empty",
		},
		{
			name: "conflicting DSN aliases",
			mutate: func(environment map[string]string) {
				environment["DATABASE_URL"] = "postgres://other.invalid/releasefoundry"
			},
			want: "conflicting",
		},
		{
			name: "required value with surrounding whitespace",
			mutate: func(environment map[string]string) {
				environment["RELEASEFOUNDRY_IDENTITY_DELIVERY_LEASE_OWNER"] = " worker-1"
			},
			want: "invalid whitespace",
		},
		{
			name: "remote plaintext relay",
			mutate: func(environment map[string]string) {
				environment["RELEASEFOUNDRY_IDENTITY_DELIVERY_SMS_RELAY_URL"] = "http://relay.example/v1/send"
			},
			want: "SMS_RELAY_URL is invalid",
		},
		{
			name: "loopback plaintext vault",
			mutate: func(environment map[string]string) {
				environment["RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_URL"] = "http://127.0.0.1:9001/v1/open"
			},
			want: "VAULT_URL is invalid",
		},
		{
			name: "partial relay mTLS profile",
			mutate: func(environment map[string]string) {
				delete(environment, "RELEASEFOUNDRY_IDENTITY_DELIVERY_RELAY_MTLS_CLIENT_KEY_FILE")
			},
			want: "RELAY_MTLS_CLIENT_KEY_FILE is required",
		},
		{
			name: "conflicting shared mTLS variables",
			mutate: func(environment map[string]string) {
				environment["RELEASEFOUNDRY_IDENTITY_DELIVERY_SHARED_MTLS_CA_FILE"] = "/run/secrets/shared-ca.pem"
			},
			want: "conflicting identity delivery mTLS profile variables",
		},
		{
			name: "implicitly shared workload identity",
			mutate: func(environment map[string]string) {
				environment["RELEASEFOUNDRY_IDENTITY_DELIVERY_RELAY_MTLS_CLIENT_CERT_FILE"] = environment["RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_CERT_FILE"]
				environment["RELEASEFOUNDRY_IDENTITY_DELIVERY_RELAY_MTLS_CLIENT_KEY_FILE"] = environment["RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_KEY_FILE"]
			},
			want: "shared identity delivery mTLS credentials require shared profile mode",
		},
		{
			name: "unknown mTLS mode",
			mutate: func(environment map[string]string) {
				environment["RELEASEFOUNDRY_IDENTITY_DELIVERY_MTLS_PROFILE_MODE"] = "automatic"
			},
			want: "must be separate or shared",
		},
		{
			name: "ephemeral health port",
			mutate: func(environment map[string]string) {
				environment["RELEASEFOUNDRY_IDENTITY_DELIVERY_HEALTH_ADDRESS"] = "127.0.0.1:0"
			},
			want: "HEALTH_ADDRESS is invalid",
		},
		{
			name: "unbounded shutdown",
			mutate: func(environment map[string]string) {
				environment["RELEASEFOUNDRY_IDENTITY_DELIVERY_SHUTDOWN_TIMEOUT"] = "3m"
			},
			want: "SHUTDOWN_TIMEOUT",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			environment := identityDeliveryTestEnvironment()
			test.mutate(environment)
			_, err := identityDeliveryCommandConfigFromEnv(
				identityDeliveryMapLookup(environment),
			)
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("expected %q, got %v", test.want, err)
			}
		})
	}
}

func TestIdentityDeliveryReadinessGateLifecycle(t *testing.T) {
	calls := 0
	gate := newIdentityDeliveryReadinessGate(func(context.Context) error {
		calls++
		return nil
	})
	if err := gate.check(context.Background()); err == nil {
		t.Fatal("inactive gate reported ready")
	}
	gate.activate()
	if err := gate.check(context.Background()); err != nil {
		t.Fatalf("active gate was not ready: %v", err)
	}
	gate.drain()
	if err := gate.check(context.Background()); err == nil {
		t.Fatal("draining gate reported ready")
	}
	if calls != 1 {
		t.Fatalf("dependency called %d times, want 1", calls)
	}
}

func TestIdentityDeliveryProcessesServeReadyAndShutdownGracefully(t *testing.T) {
	listener := identityDeliveryTestListener(t)
	defer listener.Close()
	started := make(chan struct{})
	runner := identityDeliveryTestRunner{run: func(
		ctx context.Context,
		options releasefoundry.IdentityDeliveryDaemonOptions,
	) (releasefoundry.IdentityDeliveryRunResult, error) {
		close(started)
		if options.TenantID != identityDeliveryTestTenantID ||
			options.ProjectID != identityDeliveryTestProjectID {
			return releasefoundry.IdentityDeliveryRunResult{}, errors.New("scope changed")
		}
		<-ctx.Done()
		return releasefoundry.IdentityDeliveryRunResult{GracefulShutdown: true}, nil
	}}
	ctx, cancel := context.WithCancel(context.Background())
	type processResult struct {
		result releasefoundry.IdentityDeliveryRunResult
		err    error
	}
	done := make(chan processResult, 1)
	go func() {
		result, err := runIdentityDeliveryProcesses(
			ctx,
			runner,
			identityDeliveryTestDaemonOptions(),
			listener,
			func(context.Context) error { return nil },
			time.Second,
		)
		done <- processResult{result: result, err: err}
	}()
	<-started
	response := identityDeliveryWaitForProbe(t, listener.Addr().String(), "/readyz")
	if response.StatusCode != http.StatusOK {
		response.Body.Close()
		t.Fatalf("readiness status = %d", response.StatusCode)
	}
	response.Body.Close()
	cancel()
	select {
	case outcome := <-done:
		if outcome.err != nil || !outcome.result.GracefulShutdown {
			t.Fatalf("unexpected shutdown: result=%#v err=%v", outcome.result, outcome.err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("cooperative daemon did not stop")
	}
}

func TestIdentityDeliveryProcessesBoundUncooperativeWorkerShutdown(t *testing.T) {
	listener := identityDeliveryTestListener(t)
	defer listener.Close()
	started := make(chan struct{})
	release := make(chan struct{})
	defer close(release)
	runner := identityDeliveryTestRunner{run: func(
		context.Context,
		releasefoundry.IdentityDeliveryDaemonOptions,
	) (releasefoundry.IdentityDeliveryRunResult, error) {
		close(started)
		<-release
		return releasefoundry.IdentityDeliveryRunResult{}, nil
	}}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() {
		_, err := runIdentityDeliveryProcesses(
			ctx,
			runner,
			identityDeliveryTestDaemonOptions(),
			listener,
			func(context.Context) error { return nil },
			100*time.Millisecond,
		)
		done <- err
	}()
	<-started
	startedAt := time.Now()
	cancel()
	select {
	case err := <-done:
		if identityDeliveryCommandErrorCode(err) != "shutdown_timeout" {
			t.Fatalf("unexpected error: %v (%s)", err, identityDeliveryCommandErrorCode(err))
		}
		if elapsed := time.Since(startedAt); elapsed > 500*time.Millisecond {
			t.Fatalf("shutdown was not bounded: %s", elapsed)
		}
	case <-time.After(time.Second):
		t.Fatal("uncooperative worker blocked process shutdown")
	}
}

func TestIdentityDeliveryProcessesRejectUnexpectedWorkerExit(t *testing.T) {
	listener := identityDeliveryTestListener(t)
	defer listener.Close()
	runner := identityDeliveryTestRunner{run: func(
		context.Context,
		releasefoundry.IdentityDeliveryDaemonOptions,
	) (releasefoundry.IdentityDeliveryRunResult, error) {
		return releasefoundry.IdentityDeliveryRunResult{}, nil
	}}
	_, err := runIdentityDeliveryProcesses(
		context.Background(),
		runner,
		identityDeliveryTestDaemonOptions(),
		listener,
		func(context.Context) error { return nil },
		time.Second,
	)
	if identityDeliveryCommandErrorCode(err) != "worker_stopped" {
		t.Fatalf("unexpected error: %v (%s)", err, identityDeliveryCommandErrorCode(err))
	}
}

func TestIdentityDeliveryHealthHandlerDoesNotExposeReadinessFailure(t *testing.T) {
	secret := "postgres-password-that-must-not-leak"
	handler := identityDeliveryHealthHandler(func(context.Context) error {
		return errors.New(secret)
	})
	request := httptest.NewRequest(http.MethodGet, "/readyz", nil)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusServiceUnavailable ||
		strings.Contains(recorder.Body.String(), secret) ||
		recorder.Header().Get("Cache-Control") != "no-store" {
		t.Fatalf("unsafe readiness response: code=%d body=%q", recorder.Code, recorder.Body.String())
	}

	request = httptest.NewRequest(http.MethodPost, "/healthz", nil)
	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusMethodNotAllowed ||
		recorder.Header().Get("Allow") != "GET, HEAD" {
		t.Fatalf("unexpected method response: code=%d headers=%v", recorder.Code, recorder.Header())
	}
}

func TestIdentityDeliveryStructuredErrorIsSecretSafe(t *testing.T) {
	secret := "smtp-secret-value"
	err := newIdentityDeliveryCommandError(
		"worker_failed", "identity delivery worker failed", errors.New(secret),
	)
	if strings.Contains(err.Error(), secret) {
		t.Fatalf("public error exposed secret: %q", err)
	}
	var output bytes.Buffer
	logger := slog.New(slog.NewJSONHandler(&output, nil))
	logIdentityDeliveryError(logger, "daemon_failed", err)
	if strings.Contains(output.String(), secret) {
		t.Fatalf("structured log exposed secret: %s", output.String())
	}
	var record map[string]any
	if decodeErr := json.Unmarshal(output.Bytes(), &record); decodeErr != nil {
		t.Fatal(decodeErr)
	}
	if record["event"] != "daemon_failed" || record["error_code"] != "worker_failed" {
		t.Fatalf("unexpected structured log: %#v", record)
	}

	output.Reset()
	logIdentityDeliveryError(logger, "daemon_failed", errors.New(secret))
	if strings.Contains(output.String(), secret) {
		t.Fatalf("untyped error exposed secret: %s", output.String())
	}
}

func identityDeliveryTestEnvironment() map[string]string {
	return map[string]string{
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_POSTGRES_DSN":                "postgres://worker:private@127.0.0.1/releasefoundry?sslmode=disable",
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_TENANT_ID":                   identityDeliveryTestTenantID,
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_PROJECT_ID":                  identityDeliveryTestProjectID,
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_LEASE_OWNER":                 "worker-1",
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_URL":                   "https://vault.internal/v1/open",
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_EMAIL_RELAY_URL":             "https://relay.internal/v1/email/send",
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_SMS_RELAY_URL":               "https://relay.internal/v1/sms/send",
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_MTLS_PROFILE_MODE":           "separate",
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_CA_FILE":          "/run/secrets/vault-ca.pem",
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_CERT_FILE": "/run/secrets/vault-cert.pem",
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_KEY_FILE":  "/run/secrets/vault-key.pem",
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_SERVER_NAME":      "vault.internal",
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_RELAY_MTLS_CA_FILE":          "/run/secrets/relay-ca.pem",
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_RELAY_MTLS_CLIENT_CERT_FILE": "/run/secrets/relay-cert.pem",
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_RELAY_MTLS_CLIENT_KEY_FILE":  "/run/secrets/relay-key.pem",
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_RELAY_MTLS_SERVER_NAME":      "relay.internal",
	}
}

func identityDeliveryMapLookup(
	environment map[string]string,
) func(string) (string, bool) {
	return func(key string) (string, bool) {
		value, present := environment[key]
		return value, present
	}
}

func identityDeliveryTestListener(t *testing.T) net.Listener {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	return listener
}

func identityDeliveryTestDaemonOptions() releasefoundry.IdentityDeliveryDaemonOptions {
	return releasefoundry.IdentityDeliveryDaemonOptions{
		TenantID: identityDeliveryTestTenantID, ProjectID: identityDeliveryTestProjectID,
		BatchSize: 10, PollInterval: time.Millisecond,
	}
}

func identityDeliveryWaitForProbe(
	t *testing.T,
	address string,
	path string,
) *http.Response {
	t.Helper()
	client := &http.Client{Timeout: 100 * time.Millisecond}
	deadline := time.Now().Add(time.Second)
	for {
		response, err := client.Get("http://" + address + path)
		if err == nil {
			return response
		}
		if time.Now().After(deadline) {
			t.Fatalf("probe never became available: %v", err)
		}
		time.Sleep(5 * time.Millisecond)
	}
}
