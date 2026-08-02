package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"regexp"
	"strconv"
	"strings"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/3351666087/release-foundry/packages/go/releasefoundry"
	_ "github.com/lib/pq"
)

const identityDeliveryCommandName = "releasefoundry-identity-delivery"

const identityDeliveryReadinessQuery = `
SELECT to_regclass('public.identity_verification_delivery_outbox') IS NOT NULL
   AND to_regclass('public.identity_verification_delivery_redrive_audit') IS NOT NULL
   AND to_regprocedure(
     'public.a1_claim_identity_delivery_outbox(uuid,uuid,text,integer,bigint,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_heartbeat_identity_delivery_outbox(uuid,uuid,uuid,text,bigint,bigint,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_complete_identity_delivery_outbox(uuid,uuid,uuid,text,bigint,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_retry_identity_delivery_outbox(uuid,uuid,uuid,text,bigint,text,timestamp with time zone,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_dead_letter_identity_delivery_outbox(uuid,uuid,uuid,text,bigint,text,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_redrive_identity_delivery_outbox(uuid,uuid,uuid,bigint,text,text,text,timestamp with time zone)'
   ) IS NOT NULL
`

var identityDeliveryCommandUUIDPattern = regexp.MustCompile(
	`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`,
)
var identityDeliveryCommandIdentifierPattern = regexp.MustCompile(
	`^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$`,
)

type identityDeliveryCommandConfig struct {
	postgresDSN            string
	tenantID               string
	projectID              string
	leaseOwner             string
	vaultURL               string
	emailRelayURL          string
	smsRelayURL            string
	browserVerificationURL string
	mtlsProfileMode        string
	vaultMTLS              identityDeliveryMTLSFileProfile
	relayMTLS              identityDeliveryMTLSFileProfile
	healthAddress          string
	batchSize              int
	maxOpenConnections     int
	maxAttempts            int
	pollInterval           time.Duration
	leaseDuration          time.Duration
	heartbeatInterval      time.Duration
	providerTimeout        time.Duration
	vaultTimeout           time.Duration
	storeTimeout           time.Duration
	telemetryTimeout       time.Duration
	baseBackoff            time.Duration
	maxBackoff             time.Duration
	readinessTimeout       time.Duration
	shutdownTimeout        time.Duration
}

type identityDeliveryDaemonRunner interface {
	Run(
		context.Context,
		releasefoundry.IdentityDeliveryDaemonOptions,
	) (releasefoundry.IdentityDeliveryRunResult, error)
}

type identityDeliveryReadiness func(context.Context) error

func main() {
	os.Exit(runIdentityDeliveryMain())
}

func runIdentityDeliveryMain() int {
	logger := slog.New(slog.NewJSONHandler(os.Stderr, &slog.HandlerOptions{}))
	config, err := identityDeliveryCommandConfigFromEnv(os.LookupEnv)
	if err != nil {
		logIdentityDeliveryError(
			logger,
			"configuration_rejected",
			newIdentityDeliveryCommandError(
				"invalid_configuration",
				"identity delivery configuration was rejected",
				err,
			),
		)
		return 2
	}

	ctx, stop := signal.NotifyContext(
		context.Background(), os.Interrupt, syscall.SIGTERM,
	)
	defer stop()
	result, err := runIdentityDeliveryCommand(ctx, config)
	if err != nil {
		logIdentityDeliveryError(logger, "daemon_failed", err)
		return 1
	}
	logger.Info(
		"identity delivery daemon stopped",
		slog.String("event", "daemon_stopped"),
		slog.Bool("graceful", result.GracefulShutdown),
		slog.Int("batches", result.Batches),
		slog.Int("delivered", result.Delivered),
		slog.Int("retried", result.Retried),
		slog.Int("dead_lettered", result.DeadLettered),
	)
	return 0
}

func runIdentityDeliveryCommand(
	ctx context.Context,
	config identityDeliveryCommandConfig,
) (releasefoundry.IdentityDeliveryRunResult, error) {
	if err := config.validate(); err != nil {
		return releasefoundry.IdentityDeliveryRunResult{}, newIdentityDeliveryCommandError(
			"invalid_configuration", "identity delivery configuration was rejected", err,
		)
	}
	if ctx == nil {
		return releasefoundry.IdentityDeliveryRunResult{}, newIdentityDeliveryCommandError(
			"invalid_context", "identity delivery root context is required", nil,
		)
	}
	db, err := sql.Open("postgres", config.postgresDSN)
	if err != nil {
		return releasefoundry.IdentityDeliveryRunResult{}, errors.New(
			"open identity delivery PostgreSQL failed",
		)
	}
	db.SetMaxOpenConns(config.maxOpenConnections)
	db.SetMaxIdleConns(config.maxOpenConnections)
	defer db.Close()

	ready := postgresIdentityDeliveryReadiness(
		db, config.readinessTimeout,
	)
	readyCtx, cancel := context.WithTimeout(ctx, config.readinessTimeout)
	err = ready(readyCtx)
	cancel()
	if err != nil {
		return releasefoundry.IdentityDeliveryRunResult{}, err
	}

	store, err := releasefoundry.NewPostgresIdentityDeliveryOutboxStore(db)
	if err != nil {
		return releasefoundry.IdentityDeliveryRunResult{}, errors.New(
			"configure identity delivery PostgreSQL store failed",
		)
	}
	vaultClient, err := newIdentityDeliveryMTLSHTTPClient(
		config.vaultMTLS, config.vaultTimeout,
	)
	if err != nil {
		return releasefoundry.IdentityDeliveryRunResult{}, errors.New(
			"configure identity delivery vault mTLS client failed",
		)
	}
	providerClient, err := newIdentityDeliveryMTLSHTTPClient(
		config.relayMTLS, config.providerTimeout,
	)
	if err != nil {
		vaultClient.CloseIdleConnections()
		return releasefoundry.IdentityDeliveryRunResult{}, errors.New(
			"configure identity delivery relay mTLS client failed",
		)
	}
	defer vaultClient.CloseIdleConnections()
	defer providerClient.CloseIdleConnections()
	vault := &identityDeliveryHTTPVault{
		endpoint: config.vaultURL,
		client:   vaultClient,
		timeout:  config.vaultTimeout,
	}
	emailRelay := &identityDeliveryHTTPAdapter{
		endpoint:               config.emailRelayURL,
		channel:                releasefoundry.IdentityVerificationEmail,
		client:                 providerClient,
		timeout:                config.providerTimeout,
		browserVerificationURL: config.browserVerificationURL,
	}
	smsRelay := &identityDeliveryHTTPAdapter{
		endpoint: config.smsRelayURL,
		channel:  releasefoundry.IdentityVerificationPhone,
		client:   providerClient,
		timeout:  config.providerTimeout,
	}
	worker, err := releasefoundry.NewIdentityDeliveryWorker(
		releasefoundry.IdentityDeliveryWorkerOptions{
			Store:             store,
			Vault:             vault,
			SMTP:              emailRelay,
			SMS:               smsRelay,
			LeaseOwner:        config.leaseOwner,
			LeaseDuration:     config.leaseDuration,
			HeartbeatInterval: config.heartbeatInterval,
			ProviderTimeout:   config.providerTimeout,
			VaultTimeout:      config.vaultTimeout,
			StoreTimeout:      config.storeTimeout,
			TelemetryTimeout:  config.telemetryTimeout,
			BaseBackoff:       config.baseBackoff,
			MaxBackoff:        config.maxBackoff,
			MaxAttempts:       config.maxAttempts,
		},
	)
	if err != nil {
		return releasefoundry.IdentityDeliveryRunResult{}, fmt.Errorf(
			"configure identity delivery worker: %w", err,
		)
	}
	listener, err := net.Listen("tcp", config.healthAddress)
	if err != nil {
		return releasefoundry.IdentityDeliveryRunResult{}, errors.New(
			"listen for identity delivery health checks failed",
		)
	}
	defer listener.Close()
	return runIdentityDeliveryProcesses(
		ctx,
		worker,
		releasefoundry.IdentityDeliveryDaemonOptions{
			TenantID: config.tenantID, ProjectID: config.projectID,
			BatchSize: config.batchSize, PollInterval: config.pollInterval,
		},
		listener,
		ready,
		config.shutdownTimeout,
	)
}

func runIdentityDeliveryProcesses(
	ctx context.Context,
	runner identityDeliveryDaemonRunner,
	options releasefoundry.IdentityDeliveryDaemonOptions,
	listener net.Listener,
	readiness identityDeliveryReadiness,
	shutdownTimeout time.Duration,
) (releasefoundry.IdentityDeliveryRunResult, error) {
	if ctx == nil || runner == nil || listener == nil || readiness == nil {
		return releasefoundry.IdentityDeliveryRunResult{}, errors.New(
			"identity delivery process dependencies are required",
		)
	}
	if shutdownTimeout < 100*time.Millisecond || shutdownTimeout > 2*time.Minute {
		return releasefoundry.IdentityDeliveryRunResult{}, errors.New(
			"identity delivery shutdown timeout must be between 100ms and 2m",
		)
	}
	runCtx, cancel := context.WithCancel(ctx)
	defer cancel()
	readinessGate := newIdentityDeliveryReadinessGate(readiness)
	server := &http.Server{
		Handler:           identityDeliveryHealthHandler(readinessGate.check),
		ReadHeaderTimeout: 2 * time.Second,
		ReadTimeout:       3 * time.Second,
		WriteTimeout:      35 * time.Second,
		IdleTimeout:       30 * time.Second,
		MaxHeaderBytes:    8 * 1024,
	}
	serverErrors := make(chan error, 1)
	go func() {
		err := server.Serve(listener)
		if errors.Is(err, http.ErrServerClosed) {
			err = nil
		}
		serverErrors <- err
	}()

	type workerResult struct {
		result releasefoundry.IdentityDeliveryRunResult
		err    error
	}
	workerResults := make(chan workerResult, 1)
	go func() {
		result, err := runner.Run(runCtx, options)
		workerResults <- workerResult{result: result, err: err}
	}()
	readinessGate.activate()

	var outcome workerResult
	var serverErr error
	workerDone := false
	serverDone := false
	workerStoppedFirst := false
	select {
	case outcome = <-workerResults:
		workerDone = true
		workerStoppedFirst = true
	case serverErr = <-serverErrors:
		serverDone = true
	case <-ctx.Done():
	}
	readinessGate.drain()
	cancel()
	shutdownCtx, shutdownCancel := context.WithTimeout(
		context.Background(), shutdownTimeout,
	)
	defer shutdownCancel()
	shutdownResults := make(chan error, 1)
	go func() { shutdownResults <- server.Shutdown(shutdownCtx) }()

	if !workerDone {
		select {
		case outcome = <-workerResults:
			workerDone = true
		case <-shutdownCtx.Done():
			_ = server.Close()
			return outcome.result, newIdentityDeliveryCommandError(
				"shutdown_timeout",
				"identity delivery worker exceeded the shutdown deadline",
				shutdownCtx.Err(),
			)
		}
	}
	var shutdownErr error
	select {
	case shutdownErr = <-shutdownResults:
	case <-shutdownCtx.Done():
		_ = server.Close()
		return outcome.result, newIdentityDeliveryCommandError(
			"shutdown_timeout",
			"identity delivery health server exceeded the shutdown deadline",
			shutdownCtx.Err(),
		)
	}
	if !serverDone {
		select {
		case serverErr = <-serverErrors:
			serverDone = true
		default:
		}
	}
	if serverErr != nil {
		return outcome.result, newIdentityDeliveryCommandError(
			"health_server_failed", "identity delivery health server failed", serverErr,
		)
	}
	if shutdownErr != nil {
		return outcome.result, newIdentityDeliveryCommandError(
			"health_server_shutdown_failed",
			"identity delivery health server shutdown failed",
			shutdownErr,
		)
	}
	if outcome.err != nil {
		return outcome.result, newIdentityDeliveryCommandError(
			"worker_failed", "identity delivery worker failed", outcome.err,
		)
	}
	if workerStoppedFirst && ctx.Err() == nil {
		return outcome.result, newIdentityDeliveryCommandError(
			"worker_stopped", "identity delivery worker stopped unexpectedly", nil,
		)
	}
	return outcome.result, nil
}

type identityDeliveryReadinessGate struct {
	accepting  atomic.Bool
	dependency identityDeliveryReadiness
}

func newIdentityDeliveryReadinessGate(
	dependency identityDeliveryReadiness,
) *identityDeliveryReadinessGate {
	return &identityDeliveryReadinessGate{dependency: dependency}
}

func (gate *identityDeliveryReadinessGate) activate() {
	if gate != nil && gate.dependency != nil {
		gate.accepting.Store(true)
	}
}

func (gate *identityDeliveryReadinessGate) drain() {
	if gate != nil {
		gate.accepting.Store(false)
	}
}

func (gate *identityDeliveryReadinessGate) check(ctx context.Context) error {
	if gate == nil || !gate.accepting.Load() || gate.dependency == nil {
		return errors.New("identity delivery daemon is not accepting work")
	}
	if ctx == nil {
		return errors.New("identity delivery readiness context is required")
	}
	return gate.dependency(ctx)
}

func postgresIdentityDeliveryReadiness(
	db *sql.DB,
	timeout time.Duration,
) identityDeliveryReadiness {
	return func(parent context.Context) error {
		if db == nil {
			return errors.New("identity delivery PostgreSQL is not configured")
		}
		if parent == nil {
			return errors.New("identity delivery readiness context is required")
		}
		ctx, cancel := context.WithTimeout(parent, timeout)
		defer cancel()
		if err := db.PingContext(ctx); err != nil {
			return errors.New("identity delivery PostgreSQL is unavailable")
		}
		var ready bool
		if err := db.QueryRowContext(ctx, identityDeliveryReadinessQuery).Scan(&ready); err != nil {
			return errors.New("identity delivery PostgreSQL readiness failed")
		}
		if !ready {
			return errors.New("identity delivery migration 014 is required")
		}
		return nil
	}
}

func identityDeliveryHealthHandler(
	readiness identityDeliveryReadiness,
) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(writer http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodGet && request.Method != http.MethodHead {
			writer.Header().Set("Allow", "GET, HEAD")
			writer.Header().Set("Cache-Control", "no-store")
			writer.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		writeIdentityDeliveryProbe(writer, http.StatusOK, "ok")
	})
	mux.HandleFunc("/readyz", func(writer http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodGet && request.Method != http.MethodHead {
			writer.Header().Set("Allow", "GET, HEAD")
			writer.Header().Set("Cache-Control", "no-store")
			writer.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		if readiness == nil || readiness(request.Context()) != nil {
			writeIdentityDeliveryProbe(writer, http.StatusServiceUnavailable, "not_ready")
			return
		}
		writeIdentityDeliveryProbe(writer, http.StatusOK, "ready")
	})
	return mux
}

func writeIdentityDeliveryProbe(
	writer http.ResponseWriter,
	status int,
	state string,
) {
	writer.Header().Set("Content-Type", "application/json")
	writer.Header().Set("Cache-Control", "no-store")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(map[string]string{"status": state})
}

func identityDeliveryCommandConfigFromEnv(
	lookup func(string) (string, bool),
) (identityDeliveryCommandConfig, error) {
	if lookup == nil {
		return identityDeliveryCommandConfig{}, errors.New(
			"identity delivery environment lookup is required",
		)
	}
	postgresDSN, err := identityDeliveryPostgresDSNFromEnv(lookup)
	if err != nil {
		return identityDeliveryCommandConfig{}, err
	}
	config := identityDeliveryCommandConfig{postgresDSN: postgresDSN}
	required := []struct {
		key         string
		destination *string
	}{
		{"RELEASEFOUNDRY_IDENTITY_DELIVERY_TENANT_ID", &config.tenantID},
		{"RELEASEFOUNDRY_IDENTITY_DELIVERY_PROJECT_ID", &config.projectID},
		{"RELEASEFOUNDRY_IDENTITY_DELIVERY_LEASE_OWNER", &config.leaseOwner},
		{"RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_URL", &config.vaultURL},
		{"RELEASEFOUNDRY_IDENTITY_DELIVERY_EMAIL_RELAY_URL", &config.emailRelayURL},
		{"RELEASEFOUNDRY_IDENTITY_DELIVERY_SMS_RELAY_URL", &config.smsRelayURL},
		{"RELEASEFOUNDRY_IDENTITY_VERIFICATION_BROWSER_URL", &config.browserVerificationURL},
	}
	for _, item := range required {
		*item.destination, err = identityDeliveryRequiredEnv(lookup, item.key)
		if err != nil {
			return identityDeliveryCommandConfig{}, err
		}
	}
	config.mtlsProfileMode, err = identityDeliveryRequiredEnv(
		lookup, "RELEASEFOUNDRY_IDENTITY_DELIVERY_MTLS_PROFILE_MODE",
	)
	if err != nil {
		return identityDeliveryCommandConfig{}, err
	}
	config.vaultMTLS, config.relayMTLS, err = identityDeliveryMTLSProfilesFromEnv(
		lookup, config.mtlsProfileMode,
	)
	if err != nil {
		return identityDeliveryCommandConfig{}, err
	}
	config.healthAddress, err = identityDeliveryOptionalEnv(
		lookup, "RELEASEFOUNDRY_IDENTITY_DELIVERY_HEALTH_ADDRESS", "127.0.0.1:8081",
	)
	if err != nil {
		return identityDeliveryCommandConfig{}, err
	}
	if config.batchSize, err = identityDeliveryEnvInt(
		lookup, "RELEASEFOUNDRY_IDENTITY_DELIVERY_BATCH_SIZE", 50,
	); err != nil {
		return identityDeliveryCommandConfig{}, err
	}
	if config.maxOpenConnections, err = identityDeliveryEnvInt(
		lookup, "RELEASEFOUNDRY_IDENTITY_DELIVERY_MAX_OPEN_CONNECTIONS", 8,
	); err != nil {
		return identityDeliveryCommandConfig{}, err
	}
	if config.maxAttempts, err = identityDeliveryEnvInt(
		lookup, "RELEASEFOUNDRY_IDENTITY_DELIVERY_MAX_ATTEMPTS", 8,
	); err != nil {
		return identityDeliveryCommandConfig{}, err
	}
	durations := []struct {
		key         string
		fallback    time.Duration
		destination *time.Duration
	}{
		{"RELEASEFOUNDRY_IDENTITY_DELIVERY_POLL_INTERVAL", time.Second, &config.pollInterval},
		{"RELEASEFOUNDRY_IDENTITY_DELIVERY_LEASE_DURATION", 30 * time.Second, &config.leaseDuration},
		{"RELEASEFOUNDRY_IDENTITY_DELIVERY_HEARTBEAT_INTERVAL", 10 * time.Second, &config.heartbeatInterval},
		{"RELEASEFOUNDRY_IDENTITY_DELIVERY_PROVIDER_TIMEOUT", 10 * time.Second, &config.providerTimeout},
		{"RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_TIMEOUT", 5 * time.Second, &config.vaultTimeout},
		{"RELEASEFOUNDRY_IDENTITY_DELIVERY_STORE_TIMEOUT", 5 * time.Second, &config.storeTimeout},
		{"RELEASEFOUNDRY_IDENTITY_DELIVERY_TELEMETRY_TIMEOUT", time.Second, &config.telemetryTimeout},
		{"RELEASEFOUNDRY_IDENTITY_DELIVERY_BASE_BACKOFF", time.Second, &config.baseBackoff},
		{"RELEASEFOUNDRY_IDENTITY_DELIVERY_MAX_BACKOFF", time.Hour, &config.maxBackoff},
		{"RELEASEFOUNDRY_IDENTITY_DELIVERY_READINESS_TIMEOUT", 2 * time.Second, &config.readinessTimeout},
		{"RELEASEFOUNDRY_IDENTITY_DELIVERY_SHUTDOWN_TIMEOUT", 20 * time.Second, &config.shutdownTimeout},
	}
	for _, item := range durations {
		*item.destination, err = identityDeliveryEnvDuration(
			lookup, item.key, item.fallback,
		)
		if err != nil {
			return identityDeliveryCommandConfig{}, err
		}
	}
	if err := config.validate(); err != nil {
		return identityDeliveryCommandConfig{}, err
	}
	return config, nil
}

func (config identityDeliveryCommandConfig) validate() error {
	if strings.TrimSpace(config.postgresDSN) == "" ||
		config.postgresDSN != strings.TrimSpace(config.postgresDSN) ||
		strings.ContainsAny(config.postgresDSN, "\x00\r\n") {
		return errors.New("RELEASEFOUNDRY_IDENTITY_DELIVERY_POSTGRES_DSN is required")
	}
	if !identityDeliveryCommandUUIDPattern.MatchString(config.tenantID) {
		return errors.New("RELEASEFOUNDRY_IDENTITY_DELIVERY_TENANT_ID must be a canonical UUID")
	}
	if !identityDeliveryCommandUUIDPattern.MatchString(config.projectID) {
		return errors.New("RELEASEFOUNDRY_IDENTITY_DELIVERY_PROJECT_ID must be a canonical UUID")
	}
	if !identityDeliveryCommandIdentifierPattern.MatchString(config.leaseOwner) {
		return errors.New("RELEASEFOUNDRY_IDENTITY_DELIVERY_LEASE_OWNER is invalid")
	}
	for key, value := range map[string]string{
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_URL":       config.vaultURL,
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_EMAIL_RELAY_URL": config.emailRelayURL,
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_SMS_RELAY_URL":   config.smsRelayURL,
	} {
		if err := validateIdentityDeliveryEndpoint(value); err != nil {
			return fmt.Errorf("%s is invalid", key)
		}
	}
	if _, err := releasefoundry.BuildIdentityVerificationBrowserURL(
		config.browserVerificationURL,
		"ivc_000000000000000000000000000000000000",
		releasefoundry.IdentityVerificationBinding,
	); err != nil {
		return errors.New("RELEASEFOUNDRY_IDENTITY_VERIFICATION_BROWSER_URL is invalid")
	}
	if config.mtlsProfileMode != identityDeliveryMTLSProfileModeSeparate &&
		config.mtlsProfileMode != identityDeliveryMTLSProfileModeShared {
		return errors.New("RELEASEFOUNDRY_IDENTITY_DELIVERY_MTLS_PROFILE_MODE must be separate or shared")
	}
	if err := config.vaultMTLS.validate(); err != nil {
		return errors.New("identity delivery vault mTLS profile is invalid")
	}
	if err := config.relayMTLS.validate(); err != nil {
		return errors.New("identity delivery relay mTLS profile is invalid")
	}
	if config.mtlsProfileMode == identityDeliveryMTLSProfileModeSeparate &&
		config.vaultMTLS.clientCertificateFile == config.relayMTLS.clientCertificateFile &&
		config.vaultMTLS.clientPrivateKeyFile == config.relayMTLS.clientPrivateKeyFile {
		return errors.New("shared identity delivery mTLS credentials require shared profile mode")
	}
	if err := validateIdentityDeliveryListenAddress(config.healthAddress); err != nil {
		return errors.New("RELEASEFOUNDRY_IDENTITY_DELIVERY_HEALTH_ADDRESS is invalid")
	}
	if config.batchSize < 1 || config.batchSize > 500 {
		return errors.New("RELEASEFOUNDRY_IDENTITY_DELIVERY_BATCH_SIZE must be between 1 and 500")
	}
	if config.maxOpenConnections < 2 || config.maxOpenConnections > 100 {
		return errors.New("RELEASEFOUNDRY_IDENTITY_DELIVERY_MAX_OPEN_CONNECTIONS must be between 2 and 100")
	}
	if config.maxAttempts < 1 || config.maxAttempts > 1000 {
		return errors.New("RELEASEFOUNDRY_IDENTITY_DELIVERY_MAX_ATTEMPTS must be between 1 and 1000")
	}
	if config.pollInterval < time.Millisecond || config.pollInterval > time.Minute {
		return errors.New("RELEASEFOUNDRY_IDENTITY_DELIVERY_POLL_INTERVAL must be between 1ms and 1m")
	}
	if config.leaseDuration < 100*time.Millisecond || config.leaseDuration > time.Hour {
		return errors.New("RELEASEFOUNDRY_IDENTITY_DELIVERY_LEASE_DURATION must be between 100ms and 1h")
	}
	if config.heartbeatInterval < time.Millisecond ||
		config.heartbeatInterval >= config.leaseDuration/2 {
		return errors.New("RELEASEFOUNDRY_IDENTITY_DELIVERY_HEARTBEAT_INTERVAL must be shorter than half the lease")
	}
	for key, value := range map[string]time.Duration{
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_PROVIDER_TIMEOUT":  config.providerTimeout,
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_TIMEOUT":     config.vaultTimeout,
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_STORE_TIMEOUT":     config.storeTimeout,
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_TELEMETRY_TIMEOUT": config.telemetryTimeout,
	} {
		if value < time.Millisecond || value >= config.leaseDuration {
			return fmt.Errorf("%s must be at least 1ms and shorter than the lease", key)
		}
	}
	if config.baseBackoff < time.Millisecond ||
		config.maxBackoff < config.baseBackoff ||
		config.maxBackoff > 24*time.Hour {
		return errors.New("identity delivery backoff configuration is invalid")
	}
	if config.readinessTimeout < 100*time.Millisecond ||
		config.readinessTimeout > 30*time.Second {
		return errors.New("RELEASEFOUNDRY_IDENTITY_DELIVERY_READINESS_TIMEOUT must be between 100ms and 30s")
	}
	if config.shutdownTimeout < 100*time.Millisecond ||
		config.shutdownTimeout > 2*time.Minute {
		return errors.New("RELEASEFOUNDRY_IDENTITY_DELIVERY_SHUTDOWN_TIMEOUT must be between 100ms and 2m")
	}
	return nil
}

func validateIdentityDeliveryEndpoint(value string) error {
	parsed, err := url.Parse(value)
	if err != nil || parsed.Host == "" || parsed.Path == "" ||
		parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" {
		return errors.New("invalid endpoint")
	}
	if parsed.Scheme != "https" {
		return errors.New("endpoint must use HTTPS with mutual TLS")
	}
	return nil
}

const (
	identityDeliveryMTLSProfileModeSeparate = "separate"
	identityDeliveryMTLSProfileModeShared   = "shared"
)

type identityDeliveryMTLSFileProfile struct {
	caBundleFile          string
	clientCertificateFile string
	clientPrivateKeyFile  string
	serverName            string
}

func (profile identityDeliveryMTLSFileProfile) validate() error {
	values := []string{
		profile.caBundleFile,
		profile.clientCertificateFile,
		profile.clientPrivateKeyFile,
		profile.serverName,
	}
	for _, value := range values {
		if value == "" || value != strings.TrimSpace(value) ||
			strings.ContainsAny(value, "\x00\r\n") {
			return errors.New("invalid mTLS profile")
		}
	}
	if len(profile.serverName) > 253 ||
		strings.ContainsAny(profile.serverName, "/:\\") {
		return errors.New("invalid mTLS server name")
	}
	return nil
}

func identityDeliveryMTLSProfilesFromEnv(
	lookup func(string) (string, bool),
	mode string,
) (identityDeliveryMTLSFileProfile, identityDeliveryMTLSFileProfile, error) {
	const (
		sharedCA   = "RELEASEFOUNDRY_IDENTITY_DELIVERY_SHARED_MTLS_CA_FILE"
		sharedCert = "RELEASEFOUNDRY_IDENTITY_DELIVERY_SHARED_MTLS_CLIENT_CERT_FILE"
		sharedKey  = "RELEASEFOUNDRY_IDENTITY_DELIVERY_SHARED_MTLS_CLIENT_KEY_FILE"
		vaultCA    = "RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_CA_FILE"
		vaultCert  = "RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_CERT_FILE"
		vaultKey   = "RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_KEY_FILE"
		relayCA    = "RELEASEFOUNDRY_IDENTITY_DELIVERY_RELAY_MTLS_CA_FILE"
		relayCert  = "RELEASEFOUNDRY_IDENTITY_DELIVERY_RELAY_MTLS_CLIENT_CERT_FILE"
		relayKey   = "RELEASEFOUNDRY_IDENTITY_DELIVERY_RELAY_MTLS_CLIENT_KEY_FILE"
		vaultName  = "RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_SERVER_NAME"
		relayName  = "RELEASEFOUNDRY_IDENTITY_DELIVERY_RELAY_MTLS_SERVER_NAME"
	)
	sharedKeys := []string{sharedCA, sharedCert, sharedKey}
	separateKeys := []string{vaultCA, vaultCert, vaultKey, relayCA, relayCert, relayKey}
	var vaultProfile, relayProfile identityDeliveryMTLSFileProfile
	var err error
	switch mode {
	case identityDeliveryMTLSProfileModeShared:
		if err = rejectIdentityDeliveryMTLSEnvKeys(lookup, separateKeys); err != nil {
			return vaultProfile, relayProfile, err
		}
		vaultProfile.caBundleFile, err = identityDeliveryRequiredEnv(lookup, sharedCA)
		if err == nil {
			vaultProfile.clientCertificateFile, err = identityDeliveryRequiredEnv(lookup, sharedCert)
		}
		if err == nil {
			vaultProfile.clientPrivateKeyFile, err = identityDeliveryRequiredEnv(lookup, sharedKey)
		}
		if err != nil {
			return identityDeliveryMTLSFileProfile{}, identityDeliveryMTLSFileProfile{}, err
		}
		relayProfile.caBundleFile = vaultProfile.caBundleFile
		relayProfile.clientCertificateFile = vaultProfile.clientCertificateFile
		relayProfile.clientPrivateKeyFile = vaultProfile.clientPrivateKeyFile
	case identityDeliveryMTLSProfileModeSeparate:
		if err = rejectIdentityDeliveryMTLSEnvKeys(lookup, sharedKeys); err != nil {
			return vaultProfile, relayProfile, err
		}
		bindings := []struct {
			key         string
			destination *string
		}{
			{vaultCA, &vaultProfile.caBundleFile},
			{vaultCert, &vaultProfile.clientCertificateFile},
			{vaultKey, &vaultProfile.clientPrivateKeyFile},
			{relayCA, &relayProfile.caBundleFile},
			{relayCert, &relayProfile.clientCertificateFile},
			{relayKey, &relayProfile.clientPrivateKeyFile},
		}
		for _, binding := range bindings {
			*binding.destination, err = identityDeliveryRequiredEnv(lookup, binding.key)
			if err != nil {
				return identityDeliveryMTLSFileProfile{}, identityDeliveryMTLSFileProfile{}, err
			}
		}
	default:
		return vaultProfile, relayProfile, errors.New(
			"RELEASEFOUNDRY_IDENTITY_DELIVERY_MTLS_PROFILE_MODE must be separate or shared",
		)
	}
	vaultProfile.serverName, err = identityDeliveryRequiredEnv(lookup, vaultName)
	if err == nil {
		relayProfile.serverName, err = identityDeliveryRequiredEnv(lookup, relayName)
	}
	if err != nil {
		return identityDeliveryMTLSFileProfile{}, identityDeliveryMTLSFileProfile{}, err
	}
	return vaultProfile, relayProfile, nil
}

func rejectIdentityDeliveryMTLSEnvKeys(
	lookup func(string) (string, bool),
	keys []string,
) error {
	for _, key := range keys {
		_, present := lookup(key)
		if present {
			return errors.New("conflicting identity delivery mTLS profile variables are set")
		}
	}
	return nil
}

func validateIdentityDeliveryListenAddress(value string) error {
	host, portValue, err := net.SplitHostPort(value)
	if err != nil || strings.TrimSpace(host) == "" {
		return errors.New("invalid listen address")
	}
	port, err := strconv.Atoi(portValue)
	if err != nil || port < 1 || port > 65535 {
		return errors.New("invalid listen port")
	}
	return nil
}

func identityDeliveryPostgresDSNFromEnv(
	lookup func(string) (string, bool),
) (string, error) {
	keys := []string{
		"RELEASEFOUNDRY_IDENTITY_DELIVERY_POSTGRES_DSN",
		"RELEASEFOUNDRY_POSTGRES_DSN",
		"DATABASE_URL",
	}
	selected := ""
	for _, key := range keys {
		value, present, err := identityDeliveryEnvValue(lookup, key)
		if err != nil {
			return "", err
		}
		if !present {
			continue
		}
		if selected != "" && selected != value {
			return "", errors.New(
				"conflicting identity delivery PostgreSQL DSN variables are set",
			)
		}
		selected = value
	}
	if selected == "" {
		return "", errors.New("RELEASEFOUNDRY_IDENTITY_DELIVERY_POSTGRES_DSN is required")
	}
	return selected, nil
}

func identityDeliveryEnvValue(
	lookup func(string) (string, bool),
	key string,
) (string, bool, error) {
	value, present := lookup(key)
	if !present {
		return "", false, nil
	}
	if value == "" || strings.TrimSpace(value) == "" {
		return "", true, fmt.Errorf("%s must not be empty", key)
	}
	if value != strings.TrimSpace(value) || strings.ContainsAny(value, "\x00\r\n") {
		return "", true, fmt.Errorf("%s contains invalid whitespace", key)
	}
	return value, true, nil
}

func identityDeliveryRequiredEnv(
	lookup func(string) (string, bool),
	key string,
) (string, error) {
	value, present, err := identityDeliveryEnvValue(lookup, key)
	if err != nil {
		return "", err
	}
	if !present {
		return "", fmt.Errorf("%s is required", key)
	}
	return value, nil
}

func identityDeliveryOptionalEnv(
	lookup func(string) (string, bool),
	key string,
	fallback string,
) (string, error) {
	value, present, err := identityDeliveryEnvValue(lookup, key)
	if err != nil {
		return "", err
	}
	if !present {
		return fallback, nil
	}
	return value, nil
}

func identityDeliveryEnvInt(
	lookup func(string) (string, bool),
	key string,
	fallback int,
) (int, error) {
	value, present, err := identityDeliveryEnvValue(lookup, key)
	if err != nil {
		return 0, err
	}
	if !present {
		return fallback, nil
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return 0, fmt.Errorf("%s must be an integer", key)
	}
	return parsed, nil
}

func identityDeliveryEnvDuration(
	lookup func(string) (string, bool),
	key string,
	fallback time.Duration,
) (time.Duration, error) {
	value, present, err := identityDeliveryEnvValue(lookup, key)
	if err != nil {
		return 0, err
	}
	if !present {
		return fallback, nil
	}
	parsed, err := time.ParseDuration(value)
	if err != nil {
		return 0, fmt.Errorf("%s must be a Go duration", key)
	}
	return parsed, nil
}
