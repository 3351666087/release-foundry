package main

import (
	"context"
	"crypto/tls"
	"database/sql"
	"errors"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/ashr-labs/ashr/packages/go/ashrclone"
)

func TestProductionIdentitySecurityRuntimeConfigIsExplicitAndAllOrNone(t *testing.T) {
	runtimeDSN := "postgres://runtime-role.invalid/ashr"
	config, err := productionIdentitySecurityRuntimeConfigFromEnv(
		lookup(map[string]string{}),
		runtimeDSN,
	)
	if err != nil || config != nil {
		t.Fatalf("disabled security runtime was not inert: config=%#v err=%v", config, err)
	}
	values := productionIdentitySecurityRuntimeTestEnv(t)
	delete(values, "ASHR_IDENTITY_SECURITY_ENABLED")
	_, err = productionIdentitySecurityRuntimeConfigFromEnv(
		lookup(values),
		runtimeDSN,
	)
	if err == nil || !strings.Contains(err.Error(), "ENABLED=true") {
		t.Fatalf("dangling security configuration was accepted: %v", err)
	}
	assertErrorOmitsValues(t, err, values)

	base := productionIdentitySecurityRuntimeTestEnv(t)
	for _, missing := range []string{
		"ASHR_IDENTITY_SECURITY_TICKET_ISSUER_DSN",
		"ASHR_IDENTITY_SECURITY_PROCESS_URL",
		"ASHR_IDENTITY_SECURITY_CONFIRM_URL",
		"ASHR_IDENTITY_SECURITY_HANDOFF_CONSUME_URL",
		"ASHR_IDENTITY_SECURITY_CLEANUP_URL",
		"ASHR_IDENTITY_SECURITY_MTLS_CA_FILE",
		"ASHR_IDENTITY_SECURITY_MTLS_CLIENT_CERT_FILE",
		"ASHR_IDENTITY_SECURITY_MTLS_CLIENT_KEY_FILE",
		"ASHR_IDENTITY_SECURITY_MTLS_SERVER_NAME",
		"ASHR_IDENTITY_SECURITY_ORGANIZATION_ID",
		"ASHR_IDENTITY_SECURITY_PROJECT_ID",
	} {
		t.Run(missing, func(t *testing.T) {
			partial := cloneStrings(base)
			delete(partial, missing)
			_, configErr := productionIdentitySecurityRuntimeConfigFromEnv(
				lookup(partial),
				runtimeDSN,
			)
			if configErr == nil ||
				!strings.Contains(configErr.Error(), "all-or-none") ||
				!strings.Contains(configErr.Error(), missing) {
				t.Fatalf("partial security configuration was accepted: %v", configErr)
			}
			assertErrorOmitsValues(t, configErr, partial)
		})
	}
}

func TestProductionIdentitySecurityRuntimeConfigRejectsSharedDSNAndUnsafeValues(t *testing.T) {
	values := productionIdentitySecurityRuntimeTestEnv(t)
	values["ASHR_IDENTITY_SECURITY_TICKET_ISSUER_DSN"] =
		"POSTGRESQL://runtime-role.invalid/ashr?application_name=ashr"
	runtimeDSN := "postgres://runtime-role.invalid/ashr?application_name=ashr"
	_, err := productionIdentitySecurityRuntimeConfigFromEnv(
		lookup(values),
		runtimeDSN,
	)
	if err == nil || !strings.Contains(err.Error(), "independent database DSN") {
		t.Fatalf("shared normalized DSN was accepted: %v", err)
	}
	assertErrorOmitsValues(t, err, values)

	for _, test := range []struct {
		name   string
		key    string
		value  string
		needle string
	}{
		{
			name:   "invalid organization",
			key:    "ASHR_IDENTITY_SECURITY_ORGANIZATION_ID",
			value:  "organization-secret-invalid",
			needle: "canonical UUIDs",
		},
		{
			name:   "invalid timeout",
			key:    "ASHR_IDENTITY_SECURITY_REQUEST_TIMEOUT_SECONDS",
			value:  "31",
			needle: "between 1 and 30",
		},
		{
			name:   "invalid ttl",
			key:    "ASHR_IDENTITY_SECURITY_TICKET_TTL_SECONDS",
			value:  "301",
			needle: "between 1 and 300",
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			invalid := productionIdentitySecurityRuntimeTestEnv(t)
			invalid[test.key] = test.value
			_, configErr := productionIdentitySecurityRuntimeConfigFromEnv(
				lookup(invalid),
				"postgres://runtime-role.invalid/ashr",
			)
			if configErr == nil || !strings.Contains(configErr.Error(), test.needle) ||
				strings.Contains(configErr.Error(), test.value) {
				t.Fatalf("unsafe security configuration was accepted or echoed: %v", configErr)
			}
		})
	}
}

func TestProductionIdentitySecurityRuntimeBuildsRestrictedIssuerAndWiresHTTP(t *testing.T) {
	values := productionIdentitySecurityRuntimeTestEnv(t)
	config, err := productionIdentitySecurityRuntimeConfigFromEnv(
		lookup(values),
		"postgres://runtime-role.invalid/ashr",
	)
	if err != nil {
		t.Fatal(err)
	}
	issuerDB, issuerMock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	issuerMock.ExpectQuery("SELECT\\s+current_user").WillReturnRows(
		sqlmock.NewRows([]string{"ready"}).AddRow(true),
	)
	issuerMock.ExpectClose()
	originalOpen := openIdentitySecurityIssuerDatabase
	openIdentitySecurityIssuerDatabase = func(
		driverName string,
		dataSourceName string,
	) (*sql.DB, error) {
		if driverName != "postgres" ||
			dataSourceName != values["ASHR_IDENTITY_SECURITY_TICKET_ISSUER_DSN"] {
			t.Fatalf(
				"unexpected issuer database open: driver=%q dsn=%q",
				driverName,
				dataSourceName,
			)
		}
		return issuerDB, nil
	}
	t.Cleanup(func() {
		openIdentitySecurityIssuerDatabase = originalOpen
	})
	originalReady := readyIdentitySecurityProcessor
	readyCalls := 0
	readyIdentitySecurityProcessor = func(
		context.Context,
		*ashrclone.HTTPIdentitySecuritySecretProcessor,
	) error {
		readyCalls++
		return nil
	}
	t.Cleanup(func() {
		readyIdentitySecurityProcessor = originalReady
	})
	storeDB, _, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	store, err := ashrclone.NewProductionIdentityStore(
		ashrclone.ProductionIdentityStoreOptions{
			DB:                storeDB,
			SessionKey:        []byte(strings.Repeat("S", 40)),
			SessionKeyVersion: "v1",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_ = store.Close()
	})
	runtime, err := newProductionIdentitySecurityRuntime(
		context.Background(),
		config,
		store,
	)
	if err != nil {
		t.Fatal(err)
	}
	if runtime == nil || runtime.service == nil ||
		runtime.issuerDB != issuerDB || runtime.client == nil {
		t.Fatalf("security runtime is incomplete: %#v", runtime)
	}
	transport, ok := runtime.client.Transport.(*http.Transport)
	if !ok || transport.TLSClientConfig == nil ||
		transport.TLSClientConfig.MinVersion != tls.VersionTLS13 ||
		transport.TLSClientConfig.MaxVersion != tls.VersionTLS13 ||
		readyCalls != 1 {
		t.Fatalf(
			"security processor was not exact TLS 1.3 and readiness checked: calls=%d transport=%#v",
			readyCalls,
			transport,
		)
	}
	options := identityHTTPServerOptions(
		identityRuntime{
			identitySecurityService: runtime.service,
			postgres:                store,
		},
		nil,
	)
	if options.IdentitySecurityService != runtime.service ||
		options.IdentitySecurity != store ||
		options.IdentitySecurityTickets != store {
		t.Fatalf("security runtime was not wired into HTTP options: %#v", options)
	}
	if err := runtime.close(); err != nil {
		t.Fatal(err)
	}
	if err := issuerMock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestProductionIdentitySecurityRuntimeRejectsProcessorBeforeIssuerDatabase(t *testing.T) {
	values := productionIdentitySecurityRuntimeTestEnv(t)
	values["ASHR_IDENTITY_SECURITY_PROCESS_URL"] =
		"http://processor-secret.invalid/v1/process"
	_, err := productionIdentitySecurityRuntimeConfigFromEnv(
		lookup(values),
		"postgres://runtime-role.invalid/ashr",
	)
	if err == nil ||
		!strings.Contains(err.Error(), "one exact HTTPS origin") ||
		strings.Contains(err.Error(), values["ASHR_IDENTITY_SECURITY_PROCESS_URL"]) {
		t.Fatalf("invalid processor endpoint was accepted or leaked: %v", err)
	}
}

func TestProductionIdentitySecurityRuntimeRejectsReadinessBeforeIssuerDatabase(t *testing.T) {
	values := productionIdentitySecurityRuntimeTestEnv(t)
	config, err := productionIdentitySecurityRuntimeConfigFromEnv(
		lookup(values),
		"postgres://runtime-role.invalid/ashr",
	)
	if err != nil {
		t.Fatal(err)
	}
	storeDB, _, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	store, err := ashrclone.NewProductionIdentityStore(
		ashrclone.ProductionIdentityStoreOptions{
			DB:                storeDB,
			SessionKey:        []byte(strings.Repeat("S", 40)),
			SessionKeyVersion: "v1",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	opened := false
	originalOpen := openIdentitySecurityIssuerDatabase
	openIdentitySecurityIssuerDatabase = func(string, string) (*sql.DB, error) {
		opened = true
		return nil, nil
	}
	t.Cleanup(func() {
		openIdentitySecurityIssuerDatabase = originalOpen
	})
	originalReady := readyIdentitySecurityProcessor
	readyIdentitySecurityProcessor = func(
		context.Context,
		*ashrclone.HTTPIdentitySecuritySecretProcessor,
	) error {
		return errors.New("upstream included DO-NOT-REFLECT")
	}
	t.Cleanup(func() {
		readyIdentitySecurityProcessor = originalReady
	})
	_, err = newProductionIdentitySecurityRuntime(
		context.Background(),
		config,
		store,
	)
	if err == nil || opened ||
		!strings.Contains(err.Error(), "processor is unavailable") ||
		strings.Contains(err.Error(), "DO-NOT-REFLECT") {
		t.Fatalf("unready processor reached issuer database or leaked input: %v", err)
	}
}

func TestProductionIdentitySecurityRuntimeClosesIdleConnections(t *testing.T) {
	transport := &recordingCloseIdleTransport{}
	runtime := &productionIdentitySecurityRuntime{
		client: &http.Client{Transport: transport},
	}
	if err := runtime.close(); err != nil {
		t.Fatal(err)
	}
	if !transport.closed {
		t.Fatal("production identity security runtime left idle connections open")
	}
}

func TestSameNormalizedIdentityDatabaseDSN(t *testing.T) {
	for _, test := range []struct {
		left  string
		right string
		same  bool
	}{
		{
			left:  "postgres://user@DB.EXAMPLE/ashr?b=2&a=1",
			right: "postgresql://user@db.example/ashr?a=1&b=2",
			same:  true,
		},
		{
			left:  " host=db dbname=ashr user=runtime ",
			right: "host=db dbname=ashr user=runtime",
			same:  true,
		},
		{
			left:  "postgres://runtime@db.example/ashr",
			right: "postgres://issuer@db.example/ashr",
			same:  false,
		},
	} {
		if got := sameNormalizedIdentityDatabaseDSN(test.left, test.right); got != test.same {
			t.Fatalf(
				"sameNormalizedIdentityDatabaseDSN(%q,%q)=%v want %v",
				test.left,
				test.right,
				got,
				test.same,
			)
		}
	}
}

func productionIdentitySecurityRuntimeTestEnv(t *testing.T) map[string]string {
	t.Helper()
	vaultValues := productionIdentityDeliveryVaultTestEnv(t)
	return map[string]string{
		"ASHR_IDENTITY_SECURITY_ENABLED":                 "true",
		"ASHR_IDENTITY_SECURITY_TICKET_ISSUER_DSN":       "postgres://issuer-role.invalid/ashr",
		"ASHR_IDENTITY_SECURITY_PROCESS_URL":             "https://security-processor.invalid/v1/identity/security/process",
		"ASHR_IDENTITY_SECURITY_CONFIRM_URL":             "https://security-processor.invalid/v1/identity/security/confirm",
		"ASHR_IDENTITY_SECURITY_HANDOFF_CONSUME_URL":     "https://security-processor.invalid/v1/identity/security/handoff/consume",
		"ASHR_IDENTITY_SECURITY_CLEANUP_URL":             "https://security-processor.invalid/v1/identity/security/cleanup",
		"ASHR_IDENTITY_SECURITY_MTLS_CA_FILE":            vaultValues["ASHR_IDENTITY_DELIVERY_VAULT_MTLS_CA_FILE"],
		"ASHR_IDENTITY_SECURITY_MTLS_CLIENT_CERT_FILE":   vaultValues["ASHR_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_CERT_FILE"],
		"ASHR_IDENTITY_SECURITY_MTLS_CLIENT_KEY_FILE":    vaultValues["ASHR_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_KEY_FILE"],
		"ASHR_IDENTITY_SECURITY_MTLS_SERVER_NAME":        "security-processor.invalid",
		"ASHR_IDENTITY_SECURITY_ORGANIZATION_ID":         "11111111-1111-4111-8111-111111111111",
		"ASHR_IDENTITY_SECURITY_PROJECT_ID":              "22222222-2222-4222-8222-222222222222",
		"ASHR_IDENTITY_SECURITY_REQUEST_TIMEOUT_SECONDS": "9",
		"ASHR_IDENTITY_SECURITY_TICKET_TTL_SECONDS":      "240",
	}
}

func TestProductionIdentitySecurityRuntimeUsesConfiguredDurations(t *testing.T) {
	values := productionIdentitySecurityRuntimeTestEnv(t)
	config, err := productionIdentitySecurityRuntimeConfigFromEnv(
		lookup(values),
		"postgres://runtime-role.invalid/ashr",
	)
	if err != nil {
		t.Fatal(err)
	}
	if config.requestTimeout != 9*time.Second ||
		config.ticketTTL != 4*time.Minute {
		t.Fatalf(
			"security runtime durations were not preserved: timeout=%s ttl=%s",
			config.requestTimeout,
			config.ticketTTL,
		)
	}
}
