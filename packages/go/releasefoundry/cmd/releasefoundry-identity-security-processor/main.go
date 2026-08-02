package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/3351666087/release-foundry/packages/go/releasefoundry"
)

const (
	identitySecurityProcessorCommandName     = "releasefoundry-identity-security-processor"
	maxIdentitySecurityProcessorTLSFileBytes = 1024 * 1024
)

type identitySecurityProcessorCommandConfig struct {
	listenAddress               string
	serverCertificateFile       string
	serverPrivateKeyFile        string
	clientCAFile                string
	vaultDataEndpointPrefix     string
	vaultMetadataEndpointPrefix string
	vaultKeyRingEndpoint        string
	vaultNamespace              string
	vaultTokenFile              string
	vaultCAFile                 string
	vaultClientCertificateFile  string
	vaultClientPrivateKeyFile   string
	vaultServerName             string
	issuer                      string
	vaultTimeout                time.Duration
	readinessTimeout            time.Duration
	shutdownTimeout             time.Duration
}

func main() {
	os.Exit(runIdentitySecurityProcessorMain())
}

func runIdentitySecurityProcessorMain() int {
	logger := slog.New(slog.NewJSONHandler(os.Stderr, &slog.HandlerOptions{}))
	config, err := identitySecurityProcessorCommandConfigFromEnv(os.LookupEnv)
	if err != nil {
		logIdentitySecurityProcessorEvent(
			logger,
			slog.LevelError,
			"configuration_rejected",
			"invalid_configuration",
		)
		return 2
	}
	ctx, stop := signal.NotifyContext(
		context.Background(),
		os.Interrupt,
		syscall.SIGTERM,
	)
	defer stop()
	if err := runIdentitySecurityProcessor(ctx, config, logger); err != nil {
		logIdentitySecurityProcessorEvent(
			logger,
			slog.LevelError,
			"processor_failed",
			"runtime_unavailable",
		)
		return 1
	}
	logIdentitySecurityProcessorEvent(
		logger,
		slog.LevelInfo,
		"processor_stopped",
		"graceful_shutdown",
	)
	return 0
}

func identitySecurityProcessorCommandConfigFromEnv(
	lookup func(string) (string, bool),
) (identitySecurityProcessorCommandConfig, error) {
	if lookup == nil {
		return identitySecurityProcessorCommandConfig{}, errors.New(
			"identity security processor environment lookup is required",
		)
	}
	if value, present := lookup("RELEASEFOUNDRY_IDENTITY_SECURITY_VAULT_TOKEN"); present &&
		strings.TrimSpace(value) != "" {
		return identitySecurityProcessorCommandConfig{}, errors.New(
			"raw Vault token environment variables are forbidden",
		)
	}
	required := func(name string) (string, error) {
		value, present := lookup(name)
		if !present || value == "" || value != strings.TrimSpace(value) ||
			strings.ContainsAny(value, "\x00\r\n") {
			return "", fmt.Errorf("%s is required", name)
		}
		return value, nil
	}
	var config identitySecurityProcessorCommandConfig
	var err error
	for name, target := range map[string]*string{
		"RELEASEFOUNDRY_IDENTITY_SECURITY_PROCESSOR_LISTEN_ADDRESS":       &config.listenAddress,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_PROCESSOR_SERVER_CERT_FILE":     &config.serverCertificateFile,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_PROCESSOR_SERVER_KEY_FILE":      &config.serverPrivateKeyFile,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_PROCESSOR_CLIENT_CA_FILE":       &config.clientCAFile,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_VAULT_DATA_ENDPOINT_PREFIX":     &config.vaultDataEndpointPrefix,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_VAULT_METADATA_ENDPOINT_PREFIX": &config.vaultMetadataEndpointPrefix,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_VAULT_KEYRING_ENDPOINT":         &config.vaultKeyRingEndpoint,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_VAULT_TOKEN_FILE":               &config.vaultTokenFile,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_VAULT_CA_FILE":                  &config.vaultCAFile,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_VAULT_CLIENT_CERT_FILE":         &config.vaultClientCertificateFile,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_VAULT_CLIENT_KEY_FILE":          &config.vaultClientPrivateKeyFile,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_VAULT_SERVER_NAME":              &config.vaultServerName,
	} {
		*target, err = required(name)
		if err != nil {
			return identitySecurityProcessorCommandConfig{}, err
		}
	}
	config.vaultNamespace = optionalIdentitySecurityProcessorEnv(
		lookup,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_VAULT_NAMESPACE",
	)
	config.issuer = optionalIdentitySecurityProcessorEnv(
		lookup,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_TOTP_ISSUER",
	)
	if config.issuer == "" {
		config.issuer = "ReleaseFoundry"
	}
	config.vaultTimeout, err = identitySecurityProcessorDurationFromEnv(
		lookup,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_VAULT_TIMEOUT_SECONDS",
		5*time.Second,
		time.Second,
		30*time.Second,
	)
	if err != nil {
		return identitySecurityProcessorCommandConfig{}, err
	}
	config.readinessTimeout, err = identitySecurityProcessorDurationFromEnv(
		lookup,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_READINESS_TIMEOUT_SECONDS",
		5*time.Second,
		time.Second,
		30*time.Second,
	)
	if err != nil {
		return identitySecurityProcessorCommandConfig{}, err
	}
	config.shutdownTimeout, err = identitySecurityProcessorDurationFromEnv(
		lookup,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_SHUTDOWN_TIMEOUT_SECONDS",
		15*time.Second,
		time.Second,
		2*time.Minute,
	)
	if err != nil {
		return identitySecurityProcessorCommandConfig{}, err
	}
	if err := config.validate(); err != nil {
		return identitySecurityProcessorCommandConfig{}, err
	}
	return config, nil
}

func (config identitySecurityProcessorCommandConfig) validate() error {
	required := []string{
		config.listenAddress,
		config.serverCertificateFile,
		config.serverPrivateKeyFile,
		config.clientCAFile,
		config.vaultDataEndpointPrefix,
		config.vaultMetadataEndpointPrefix,
		config.vaultKeyRingEndpoint,
		config.vaultTokenFile,
		config.vaultCAFile,
		config.vaultClientCertificateFile,
		config.vaultClientPrivateKeyFile,
		config.vaultServerName,
	}
	for _, value := range required {
		if value == "" || value != strings.TrimSpace(value) ||
			strings.ContainsAny(value, "\x00\r\n\t") {
			return errors.New("identity security processor configuration is incomplete")
		}
	}
	if _, _, err := net.SplitHostPort(config.listenAddress); err != nil {
		return errors.New("identity security processor listen address is invalid")
	}
	if len(config.vaultServerName) > 253 ||
		strings.ContainsAny(config.vaultServerName, "/:@?#[]") {
		return errors.New("identity security Vault server name is invalid")
	}
	if config.vaultTimeout < time.Second || config.vaultTimeout > 30*time.Second ||
		config.readinessTimeout < time.Second ||
		config.readinessTimeout > 30*time.Second ||
		config.shutdownTimeout < time.Second ||
		config.shutdownTimeout > 2*time.Minute {
		return errors.New("identity security processor timeouts are invalid")
	}
	if len(config.issuer) > 64 ||
		strings.ContainsAny(config.issuer, "\x00\r\n\t:/?#[]@") {
		return errors.New("identity security TOTP issuer is invalid")
	}
	return nil
}

func runIdentitySecurityProcessor(
	ctx context.Context,
	config identitySecurityProcessorCommandConfig,
	logger *slog.Logger,
) error {
	if ctx == nil || logger == nil {
		return errors.New("identity security processor runtime dependencies are required")
	}
	if err := config.validate(); err != nil {
		return err
	}
	serverTLS, err := newIdentitySecurityProcessorServerTLSConfig(config)
	if err != nil {
		return errors.New("identity security processor server TLS configuration failed")
	}
	vaultClient, err := newIdentitySecurityProcessorVaultHTTPClient(config)
	if err != nil {
		return errors.New("identity security processor Vault TLS configuration failed")
	}
	defer vaultClient.CloseIdleConnections()
	tokenProvider := releasefoundry.FileIdentitySecurityVaultTokenProvider{
		Path: config.vaultTokenFile,
	}
	vault, err := releasefoundry.NewHashiCorpVaultKVV2IdentitySecurityProcessorVault(
		releasefoundry.HashiCorpVaultKVV2IdentitySecurityProcessorVaultOptions{
			DataEndpointPrefix:     config.vaultDataEndpointPrefix,
			MetadataEndpointPrefix: config.vaultMetadataEndpointPrefix,
			Namespace:              config.vaultNamespace,
			Client:                 vaultClient,
			TokenProvider:          tokenProvider,
			Timeout:                config.vaultTimeout,
		},
	)
	if err != nil {
		return errors.New("identity security processor Vault adapter configuration failed")
	}
	keys, err := releasefoundry.NewHashiCorpVaultKVV2IdentitySecurityProcessorKeyResolver(
		releasefoundry.HashiCorpVaultKVV2IdentitySecurityProcessorKeyResolverOptions{
			Endpoint:      config.vaultKeyRingEndpoint,
			Namespace:     config.vaultNamespace,
			Client:        vaultClient,
			TokenProvider: tokenProvider,
			Timeout:       config.vaultTimeout,
		},
	)
	if err != nil {
		return errors.New("identity security processor key resolver configuration failed")
	}
	processor, err := releasefoundry.NewVaultIdentitySecuritySecretProcessor(
		releasefoundry.VaultIdentitySecuritySecretProcessorOptions{
			Vault:  vault,
			Keys:   keys,
			Issuer: config.issuer,
		},
	)
	if err != nil {
		return errors.New("identity security processor initialization failed")
	}
	readyCtx, readyCancel := context.WithTimeout(ctx, config.readinessTimeout)
	err = processor.Ready(readyCtx)
	readyCancel()
	if err != nil {
		return errors.New("identity security processor startup readiness failed")
	}
	handler, err := releasefoundry.NewIdentitySecurityProcessorHandler(
		releasefoundry.IdentitySecurityProcessorHandlerOptions{
			Processor:        processor,
			Readiness:        processor,
			ReadinessTimeout: config.readinessTimeout,
		},
	)
	if err != nil {
		return errors.New("identity security processor HTTP handler configuration failed")
	}
	listener, err := net.Listen("tcp", config.listenAddress)
	if err != nil {
		return errors.New("identity security processor listener failed")
	}
	defer listener.Close()
	tlsListener := tls.NewListener(listener, serverTLS)
	server := &http.Server{
		Handler:           handler,
		ReadHeaderTimeout: 3 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      15 * time.Second,
		IdleTimeout:       30 * time.Second,
		MaxHeaderBytes:    16 * 1024,
		ErrorLog:          slog.NewLogLogger(logger.Handler(), slog.LevelError),
	}
	serverErrors := make(chan error, 1)
	go func() {
		err := server.Serve(tlsListener)
		if errors.Is(err, http.ErrServerClosed) {
			err = nil
		}
		serverErrors <- err
	}()
	logIdentitySecurityProcessorEvent(
		logger,
		slog.LevelInfo,
		"processor_started",
		"ready",
	)
	select {
	case err := <-serverErrors:
		if err != nil {
			return errors.New("identity security processor server failed")
		}
		return nil
	case <-ctx.Done():
	}
	shutdownCtx, cancel := context.WithTimeout(
		context.Background(),
		config.shutdownTimeout,
	)
	defer cancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		_ = server.Close()
		return errors.New("identity security processor graceful shutdown failed")
	}
	select {
	case err := <-serverErrors:
		if err != nil {
			return errors.New("identity security processor server failed")
		}
		return nil
	case <-shutdownCtx.Done():
		_ = server.Close()
		return errors.New("identity security processor shutdown deadline exceeded")
	}
}

func newIdentitySecurityProcessorServerTLSConfig(
	config identitySecurityProcessorCommandConfig,
) (*tls.Config, error) {
	certificatePEM, err := readIdentitySecurityProcessorBoundedFile(
		config.serverCertificateFile,
		maxIdentitySecurityProcessorTLSFileBytes,
	)
	if err != nil {
		return nil, err
	}
	defer clear(certificatePEM)
	privateKeyPEM, err := readIdentitySecurityProcessorBoundedFile(
		config.serverPrivateKeyFile,
		maxIdentitySecurityProcessorTLSFileBytes,
	)
	if err != nil {
		return nil, err
	}
	defer clear(privateKeyPEM)
	certificate, err := tls.X509KeyPair(certificatePEM, privateKeyPEM)
	if err != nil {
		return nil, errors.New("identity security processor server certificate is invalid")
	}
	clientCAPEM, err := readIdentitySecurityProcessorBoundedFile(
		config.clientCAFile,
		maxIdentitySecurityProcessorTLSFileBytes,
	)
	if err != nil {
		return nil, err
	}
	defer clear(clientCAPEM)
	clientCAs := x509.NewCertPool()
	if !clientCAs.AppendCertsFromPEM(clientCAPEM) {
		return nil, errors.New("identity security processor client CA is invalid")
	}
	return &tls.Config{
		MinVersion:   tls.VersionTLS13,
		MaxVersion:   tls.VersionTLS13,
		Certificates: []tls.Certificate{certificate},
		ClientAuth:   tls.RequireAndVerifyClientCert,
		ClientCAs:    clientCAs,
		NextProtos:   []string{"h2", "http/1.1"},
	}, nil
}

func newIdentitySecurityProcessorVaultHTTPClient(
	config identitySecurityProcessorCommandConfig,
) (*http.Client, error) {
	caPEM, err := readIdentitySecurityProcessorBoundedFile(
		config.vaultCAFile,
		maxIdentitySecurityProcessorTLSFileBytes,
	)
	if err != nil {
		return nil, err
	}
	defer clear(caPEM)
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(caPEM) {
		return nil, errors.New("identity security Vault CA is invalid")
	}
	certificatePEM, err := readIdentitySecurityProcessorBoundedFile(
		config.vaultClientCertificateFile,
		maxIdentitySecurityProcessorTLSFileBytes,
	)
	if err != nil {
		return nil, err
	}
	defer clear(certificatePEM)
	privateKeyPEM, err := readIdentitySecurityProcessorBoundedFile(
		config.vaultClientPrivateKeyFile,
		maxIdentitySecurityProcessorTLSFileBytes,
	)
	if err != nil {
		return nil, err
	}
	defer clear(privateKeyPEM)
	certificate, err := tls.X509KeyPair(certificatePEM, privateKeyPEM)
	if err != nil {
		return nil, errors.New("identity security Vault client certificate is invalid")
	}
	transport := &http.Transport{
		Proxy:                 http.ProxyFromEnvironment,
		ForceAttemptHTTP2:     true,
		MaxIdleConns:          16,
		MaxIdleConnsPerHost:   8,
		IdleConnTimeout:       30 * time.Second,
		TLSHandshakeTimeout:   5 * time.Second,
		ResponseHeaderTimeout: config.vaultTimeout,
		ExpectContinueTimeout: time.Second,
		TLSClientConfig: &tls.Config{
			MinVersion:   tls.VersionTLS13,
			MaxVersion:   tls.VersionTLS13,
			RootCAs:      roots,
			Certificates: []tls.Certificate{certificate},
			ServerName:   config.vaultServerName,
		},
	}
	return &http.Client{
		Transport: transport,
		Timeout:   config.vaultTimeout,
		CheckRedirect: func(*http.Request, []*http.Request) error {
			return errors.New("identity security Vault redirect refused")
		},
	}, nil
}

func readIdentitySecurityProcessorBoundedFile(
	path string,
	maxBytes int64,
) ([]byte, error) {
	if path == "" || path != strings.TrimSpace(path) ||
		strings.ContainsAny(path, "\x00\r\n") ||
		maxBytes < 1 {
		return nil, errors.New("identity security processor file path is invalid")
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, errors.New("identity security processor file is unavailable")
	}
	defer file.Close()
	payload, err := io.ReadAll(io.LimitReader(file, maxBytes+1))
	if err != nil || int64(len(payload)) > maxBytes || len(payload) == 0 {
		clear(payload)
		return nil, errors.New("identity security processor file is invalid")
	}
	return payload, nil
}

func optionalIdentitySecurityProcessorEnv(
	lookup func(string) (string, bool),
	name string,
) string {
	value, present := lookup(name)
	if !present || value == "" {
		return ""
	}
	if value != strings.TrimSpace(value) ||
		strings.ContainsAny(value, "\x00\r\n") {
		return "\x00"
	}
	return value
}

func identitySecurityProcessorDurationFromEnv(
	lookup func(string) (string, bool),
	name string,
	defaultValue time.Duration,
	minimum time.Duration,
	maximum time.Duration,
) (time.Duration, error) {
	raw, present := lookup(name)
	if !present || raw == "" {
		return defaultValue, nil
	}
	if raw != strings.TrimSpace(raw) {
		return 0, fmt.Errorf("%s is invalid", name)
	}
	seconds, err := strconv.Atoi(raw)
	if err != nil {
		return 0, fmt.Errorf("%s is invalid", name)
	}
	value := time.Duration(seconds) * time.Second
	if value < minimum || value > maximum {
		return 0, fmt.Errorf("%s is out of range", name)
	}
	return value, nil
}

func logIdentitySecurityProcessorEvent(
	logger *slog.Logger,
	level slog.Level,
	event string,
	code string,
) {
	if logger == nil {
		return
	}
	logger.Log(
		context.Background(),
		level,
		"identity security processor event",
		slog.String("component", identitySecurityProcessorCommandName),
		slog.String("event", event),
		slog.String("code", code),
	)
}
