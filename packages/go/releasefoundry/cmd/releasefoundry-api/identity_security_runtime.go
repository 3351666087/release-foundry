package main

import (
	"context"
	"crypto/tls"
	"database/sql"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/3351666087/release-foundry/packages/go/releasefoundry"
)

const (
	productionIdentitySecurityDefaultTimeout   = 10 * time.Second
	productionIdentitySecurityDefaultTicketTTL = 5 * time.Minute
)

var openIdentitySecurityIssuerDatabase = sql.Open
var readyIdentitySecurityProcessor = func(
	ctx context.Context,
	processor *releasefoundry.HTTPIdentitySecuritySecretProcessor,
) error {
	return processor.Ready(ctx)
}

type productionIdentitySecurityRuntimeConfig struct {
	issuerDSN             string
	processEndpoint       string
	confirmEndpoint       string
	prepareEndpoint       string
	finalizeEndpoint      string
	handoffEndpoint       string
	cleanupEndpoint       string
	caBundleFile          string
	clientCertificateFile string
	clientPrivateKeyFile  string
	serverName            string
	organizationID        string
	projectID             string
	requestTimeout        time.Duration
	ticketTTL             time.Duration
}

type productionIdentitySecurityRuntime struct {
	service  *releasefoundry.IdentitySecurityService
	issuerDB *sql.DB
	client   *http.Client
}

func (runtime *productionIdentitySecurityRuntime) close() error {
	if runtime == nil {
		return nil
	}
	if runtime.client != nil {
		runtime.client.CloseIdleConnections()
	}
	if runtime.issuerDB != nil {
		return runtime.issuerDB.Close()
	}
	return nil
}

func productionIdentitySecurityRuntimeConfigFromEnv(
	lookup func(string) (string, bool),
	runtimeDSN string,
) (*productionIdentitySecurityRuntimeConfig, error) {
	enabled, err := productionOAuthBooleanEnv(
		lookup,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_ENABLED",
	)
	if err != nil {
		return nil, err
	}
	requiredKeys := []string{
		"RELEASEFOUNDRY_IDENTITY_SECURITY_TICKET_ISSUER_DSN",
		"RELEASEFOUNDRY_IDENTITY_SECURITY_PROCESS_URL",
		"RELEASEFOUNDRY_IDENTITY_SECURITY_CONFIRM_URL",
		"RELEASEFOUNDRY_IDENTITY_SECURITY_MUTATION_PREPARE_URL",
		"RELEASEFOUNDRY_IDENTITY_SECURITY_MUTATION_FINALIZE_URL",
		"RELEASEFOUNDRY_IDENTITY_SECURITY_HANDOFF_CONSUME_URL",
		"RELEASEFOUNDRY_IDENTITY_SECURITY_CLEANUP_URL",
		"RELEASEFOUNDRY_IDENTITY_SECURITY_MTLS_CA_FILE",
		"RELEASEFOUNDRY_IDENTITY_SECURITY_MTLS_CLIENT_CERT_FILE",
		"RELEASEFOUNDRY_IDENTITY_SECURITY_MTLS_CLIENT_KEY_FILE",
		"RELEASEFOUNDRY_IDENTITY_SECURITY_MTLS_SERVER_NAME",
		"RELEASEFOUNDRY_IDENTITY_SECURITY_ORGANIZATION_ID",
		"RELEASEFOUNDRY_IDENTITY_SECURITY_PROJECT_ID",
	}
	optionalKeys := []string{
		"RELEASEFOUNDRY_IDENTITY_SECURITY_REQUEST_TIMEOUT_SECONDS",
		"RELEASEFOUNDRY_IDENTITY_SECURITY_TICKET_TTL_SECONDS",
	}
	if !enabled {
		for _, key := range append(requiredKeys, optionalKeys...) {
			if raw, present := lookup(key); present && strings.TrimSpace(raw) != "" {
				return nil, fmt.Errorf(
					"production identity security configuration requires RELEASEFOUNDRY_IDENTITY_SECURITY_ENABLED=true",
				)
			}
		}
		return nil, nil
	}

	values := make(map[string]string, len(requiredKeys))
	missing := make([]string, 0, len(requiredKeys))
	for _, key := range requiredKeys {
		value, valueErr := requiredProductionOAuthValue(lookup, key)
		if valueErr != nil {
			missing = append(missing, key)
			continue
		}
		values[key] = value
	}
	if len(missing) != 0 {
		return nil, fmt.Errorf(
			"production identity security configuration must be all-or-none; missing %s",
			strings.Join(missing, ", "),
		)
	}
	if !validProductionIdentitySecurityProcessorEndpoints(
		values["RELEASEFOUNDRY_IDENTITY_SECURITY_PROCESS_URL"],
		values["RELEASEFOUNDRY_IDENTITY_SECURITY_CONFIRM_URL"],
		values["RELEASEFOUNDRY_IDENTITY_SECURITY_MUTATION_PREPARE_URL"],
		values["RELEASEFOUNDRY_IDENTITY_SECURITY_MUTATION_FINALIZE_URL"],
		values["RELEASEFOUNDRY_IDENTITY_SECURITY_HANDOFF_CONSUME_URL"],
		values["RELEASEFOUNDRY_IDENTITY_SECURITY_CLEANUP_URL"],
	) {
		return nil, fmt.Errorf(
			"production identity security processor endpoints must use one exact HTTPS origin",
		)
	}
	issuerDSN := values["RELEASEFOUNDRY_IDENTITY_SECURITY_TICKET_ISSUER_DSN"]
	if sameNormalizedIdentityDatabaseDSN(runtimeDSN, issuerDSN) {
		return nil, fmt.Errorf(
			"production identity security ticket issuer must use an independent database DSN",
		)
	}
	organizationID := values["RELEASEFOUNDRY_IDENTITY_SECURITY_ORGANIZATION_ID"]
	projectID := values["RELEASEFOUNDRY_IDENTITY_SECURITY_PROJECT_ID"]
	if !validProductionOAuthUUID(organizationID) ||
		!validProductionOAuthUUID(projectID) {
		return nil, fmt.Errorf(
			"production identity security scope must use canonical UUIDs",
		)
	}
	requestTimeout, err := productionOAuthDurationSeconds(
		lookup,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_REQUEST_TIMEOUT_SECONDS",
		productionIdentitySecurityDefaultTimeout,
		1,
		30,
	)
	if err != nil {
		return nil, err
	}
	ticketTTL, err := productionOAuthDurationSeconds(
		lookup,
		"RELEASEFOUNDRY_IDENTITY_SECURITY_TICKET_TTL_SECONDS",
		productionIdentitySecurityDefaultTicketTTL,
		1,
		300,
	)
	if err != nil {
		return nil, err
	}
	return &productionIdentitySecurityRuntimeConfig{
		issuerDSN:             issuerDSN,
		processEndpoint:       values["RELEASEFOUNDRY_IDENTITY_SECURITY_PROCESS_URL"],
		confirmEndpoint:       values["RELEASEFOUNDRY_IDENTITY_SECURITY_CONFIRM_URL"],
		prepareEndpoint:       values["RELEASEFOUNDRY_IDENTITY_SECURITY_MUTATION_PREPARE_URL"],
		finalizeEndpoint:      values["RELEASEFOUNDRY_IDENTITY_SECURITY_MUTATION_FINALIZE_URL"],
		handoffEndpoint:       values["RELEASEFOUNDRY_IDENTITY_SECURITY_HANDOFF_CONSUME_URL"],
		cleanupEndpoint:       values["RELEASEFOUNDRY_IDENTITY_SECURITY_CLEANUP_URL"],
		caBundleFile:          values["RELEASEFOUNDRY_IDENTITY_SECURITY_MTLS_CA_FILE"],
		clientCertificateFile: values["RELEASEFOUNDRY_IDENTITY_SECURITY_MTLS_CLIENT_CERT_FILE"],
		clientPrivateKeyFile:  values["RELEASEFOUNDRY_IDENTITY_SECURITY_MTLS_CLIENT_KEY_FILE"],
		serverName:            values["RELEASEFOUNDRY_IDENTITY_SECURITY_MTLS_SERVER_NAME"],
		organizationID:        organizationID,
		projectID:             projectID,
		requestTimeout:        requestTimeout,
		ticketTTL:             ticketTTL,
	}, nil
}

func newProductionIdentitySecurityRuntime(
	ctx context.Context,
	config *productionIdentitySecurityRuntimeConfig,
	store *releasefoundry.ProductionIdentityStore,
) (*productionIdentitySecurityRuntime, error) {
	if config == nil {
		return nil, nil
	}
	if ctx == nil || store == nil {
		return nil, fmt.Errorf(
			"production identity security runtime dependencies are incomplete",
		)
	}
	caBundlePEM, err := readProductionIdentityDeliveryVaultPEM(
		config.caBundleFile,
		maxProductionIdentityDeliveryVaultCABundleBytes,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"production identity security mTLS trust material is unavailable",
		)
	}
	defer zeroBytes(caBundlePEM)
	clientCertificatePEM, err := readProductionIdentityDeliveryVaultPEM(
		config.clientCertificateFile,
		maxProductionIdentityDeliveryVaultIdentityBytes,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"production identity security mTLS identity material is unavailable",
		)
	}
	defer zeroBytes(clientCertificatePEM)
	clientPrivateKeyPEM, err := readProductionIdentityDeliveryVaultPEM(
		config.clientPrivateKeyFile,
		maxProductionIdentityDeliveryVaultIdentityBytes,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"production identity security mTLS identity material is unavailable",
		)
	}
	defer zeroBytes(clientPrivateKeyPEM)

	client, err := releasefoundry.NewIdentityDeliveryMTLSHTTPClient(
		releasefoundry.IdentityDeliveryMTLSClientOptions{
			CABundlePEM:           caBundlePEM,
			ClientCertificatePEM:  clientCertificatePEM,
			ClientPrivateKeyPEM:   clientPrivateKeyPEM,
			ServerName:            config.serverName,
			MinimumTLSVersion:     tls.VersionTLS13,
			MaximumTLSVersion:     tls.VersionTLS13,
			DialTimeout:           productionIdentityDeliveryVaultConnectTimeout,
			TLSHandshakeTimeout:   productionIdentityDeliveryVaultConnectTimeout,
			ResponseHeaderTimeout: config.requestTimeout,
			RequestTimeout:        config.requestTimeout,
		},
	)
	if err != nil {
		return nil, fmt.Errorf(
			"production identity security mTLS profile was rejected",
		)
	}
	runtime := &productionIdentitySecurityRuntime{client: client}
	keep := false
	defer func() {
		if !keep {
			_ = runtime.close()
		}
	}()
	processor, err := releasefoundry.NewHTTPIdentitySecuritySecretProcessor(
		releasefoundry.HTTPIdentitySecuritySecretProcessorOptions{
			ProcessEndpoint:        config.processEndpoint,
			ConfirmEndpoint:        config.confirmEndpoint,
			PrepareEndpoint:        config.prepareEndpoint,
			FinalizeEndpoint:       config.finalizeEndpoint,
			HandoffConsumeEndpoint: config.handoffEndpoint,
			CleanupEndpoint:        config.cleanupEndpoint,
			Client:                 client,
			Timeout:                config.requestTimeout,
		},
	)
	if err != nil {
		return nil, fmt.Errorf(
			"production identity security processor endpoints were rejected",
		)
	}
	readyCtx, readyCancel := context.WithTimeout(ctx, config.requestTimeout)
	if err = readyIdentitySecurityProcessor(readyCtx, processor); err != nil {
		readyCancel()
		return nil, fmt.Errorf(
			"production identity security processor is unavailable",
		)
	}
	readyCancel()
	issuerDB, err := openIdentitySecurityIssuerDatabase(
		"postgres",
		config.issuerDSN,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"open production identity security ticket issuer: invalid database configuration",
		)
	}
	runtime.issuerDB = issuerDB
	issuerDB.SetMaxOpenConns(4)
	issuerDB.SetMaxIdleConns(2)
	issuerDB.SetConnMaxIdleTime(5 * time.Minute)
	issuerDB.SetConnMaxLifetime(30 * time.Minute)
	issuer, err := releasefoundry.NewProductionIdentitySecurityTicketIssuer(
		releasefoundry.ProductionIdentitySecurityTicketIssuerOptions{
			DB: issuerDB,
		},
	)
	if err != nil {
		return nil, fmt.Errorf(
			"configure production identity security ticket issuer",
		)
	}
	issuerReadyCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	if err := issuer.Ready(issuerReadyCtx); err != nil {
		return nil, fmt.Errorf(
			"production identity security ticket issuer is unavailable",
		)
	}
	service, err := releasefoundry.NewIdentitySecurityService(
		releasefoundry.IdentitySecurityServiceOptions{
			Processor:           processor,
			TicketIssuer:        issuer,
			MutationStore:       store,
			ProcessorStateStore: store,
			MutationReplayStore: store,
			OrganizationID:      config.organizationID,
			ProjectID:           config.projectID,
			TicketTTL:           config.ticketTTL,
		},
	)
	if err != nil {
		return nil, fmt.Errorf(
			"configure production identity security service",
		)
	}
	runtime.service = service
	keep = true
	return runtime, nil
}

func validProductionIdentitySecurityProcessorEndpoints(
	processEndpoint string,
	confirmEndpoint string,
	prepareEndpoint string,
	finalizeEndpoint string,
	handoffEndpoint string,
	cleanupEndpoint string,
) bool {
	expected := []struct {
		raw  string
		path string
	}{
		{processEndpoint, "/v1/identity/security/process"},
		{confirmEndpoint, "/v1/identity/security/confirm"},
		{
			prepareEndpoint,
			"/v1/identity/security/mutations/prepare",
		},
		{
			finalizeEndpoint,
			"/v1/identity/security/mutations/finalize",
		},
		{handoffEndpoint, "/v1/identity/security/handoff/consume"},
		{cleanupEndpoint, "/v1/identity/security/cleanup"},
	}
	origin := ""
	for _, endpoint := range expected {
		if endpoint.raw == "" ||
			endpoint.raw != strings.TrimSpace(endpoint.raw) ||
			strings.ContainsAny(endpoint.raw, "\x00\r\n\t") {
			return false
		}
		parsed, err := url.ParseRequestURI(endpoint.raw)
		if err != nil || parsed.Scheme != "https" || parsed.Host == "" ||
			parsed.User != nil || parsed.RawQuery != "" ||
			parsed.Fragment != "" || parsed.Opaque != "" ||
			parsed.RawPath != "" || parsed.ForceQuery ||
			parsed.Path != endpoint.path {
			return false
		}
		currentOrigin := parsed.Scheme + "://" + parsed.Host
		if origin == "" {
			origin = currentOrigin
		} else if currentOrigin != origin {
			return false
		}
	}
	return true
}

func sameNormalizedIdentityDatabaseDSN(left string, right string) bool {
	left = strings.TrimSpace(left)
	right = strings.TrimSpace(right)
	if left == "" || right == "" {
		return false
	}
	if left == right {
		return true
	}
	normalizeURL := func(raw string) (string, bool) {
		parsed, err := url.Parse(raw)
		if err != nil || parsed.Host == "" ||
			(parsed.Scheme != "postgres" && parsed.Scheme != "postgresql") {
			return "", false
		}
		parsed.Scheme = "postgres"
		host := strings.ToLower(parsed.Hostname())
		if port := parsed.Port(); port != "" {
			host += ":" + port
		}
		parsed.Host = host
		parsed.Fragment = ""
		parsed.RawQuery = parsed.Query().Encode()
		return parsed.String(), true
	}
	normalizedLeft, leftOK := normalizeURL(left)
	normalizedRight, rightOK := normalizeURL(right)
	return leftOK && rightOK && normalizedLeft == normalizedRight
}
