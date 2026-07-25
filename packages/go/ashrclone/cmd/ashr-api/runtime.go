package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/netip"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/ashr-labs/ashr/packages/go/ashrclone"
)

const (
	maxProductionIdentityDeliveryVaultCABundleBytes = int64(1024 * 1024)
	maxProductionIdentityDeliveryVaultIdentityBytes = int64(256 * 1024)
	productionIdentityDeliveryVaultConnectTimeout   = 2 * time.Second
	productionIdentityDeliveryVaultRequestTimeout   = 10 * time.Second
	productionOAuthProviderDefaultTimeout           = 10 * time.Second
	productionOAuthFirstLoginDefaultTTL             = 10 * time.Minute
)

var openIdentityDatabase = sql.Open

type identityRuntime struct {
	mode                       string
	unifiedIdentity            *ashrclone.UnifiedIdentityService
	identityLifecycle          *ashrclone.IdentityLifecycleService
	identitySessions           ashrclone.IdentityHTTPSessionResolver
	identitySecurityService    *ashrclone.IdentitySecurityService
	postgres                   *ashrclone.ProductionIdentityStore
	outbox                     ashrclone.OAuthRevocationOutboxStore
	verification               *ashrclone.IdentityVerificationService
	verificationResponsePolicy *ashrclone.IdentityVerificationResponsePolicy
	sessionReceiptTransport    ashrclone.IdentitySessionReceiptTransport
	oauthFirstLogins           map[string]*ashrclone.OAuthFirstLoginService
	tenancy                    ashrclone.TenancyHTTPStore
	close                      func() error
}

type identitySessionPreviousKeyEnv struct {
	Version  string `json:"version"`
	Key      string `json:"key"`
	RetireAt string `json:"retire_at"`
}

type identitySessionHMACRuntimeConfig struct {
	activeVersion string
	activeKey     []byte
	previousKeys  []ashrclone.IdentitySessionHMACKey
	legacyVersion string
}

type identityLifecyclePreviousKeyEnv struct {
	Version string `json:"version"`
	Key     string `json:"key"`
}

type identityLifecycleKeyRuntimeConfig struct {
	activeVersion       string
	activeKey           []byte
	previousKeys        []ashrclone.IdentityLifecycleEncryptionKey
	lookupActiveVersion string
	lookupActiveKey     []byte
	previousLookupKeys  []ashrclone.IdentityLifecycleLookupKey
}

type productionIdentityDeliveryVaultConfig struct {
	sealURL               string
	deleteURL             string
	caBundleFile          string
	clientCertificateFile string
	clientPrivateKeyFile  string
	serverName            string
}

type productionIdentityDeliveryVaultRuntime struct {
	sealer *ashrclone.HTTPIdentityDeliveryVaultSealer
	client *http.Client
}

func (runtime *productionIdentityDeliveryVaultRuntime) close() {
	if runtime != nil && runtime.client != nil {
		runtime.client.CloseIdleConnections()
	}
}

type productionOAuthOpaqueVaultConfig struct {
	putURL                string
	getURL                string
	bindingURL            string
	deleteURL             string
	caBundleFile          string
	clientCertificateFile string
	clientPrivateKeyFile  string
	serverName            string
}

type productionOAuthOpaqueVaultRuntime struct {
	vault  *ashrclone.HTTPOAuthOpaqueVault
	client *http.Client
}

func (runtime *productionOAuthOpaqueVaultRuntime) close() {
	if runtime != nil && runtime.client != nil {
		runtime.client.CloseIdleConnections()
	}
}

type productionOAuthCredentialsRuntime struct {
	provider ashrclone.OAuthCredentialsProvider
	client   *http.Client
}

func (runtime *productionOAuthCredentialsRuntime) close() {
	if runtime != nil && runtime.client != nil {
		runtime.client.CloseIdleConnections()
	}
}

type productionOAuthFirstLoginProvider struct {
	adapter        ashrclone.OAuthProviderAdapter
	callbackURL    string
	transactionTTL time.Duration
	client         *http.Client
}

type productionOAuthFirstLoginDependencies struct {
	organizationID  string
	projectID       string
	credentials     ashrclone.OAuthCredentialsProvider
	credentialVault *productionOAuthCredentialsRuntime
	vault           *productionOAuthOpaqueVaultRuntime
	googleEnabled   bool
	githubEnabled   bool
	providers       map[string]productionOAuthFirstLoginProvider
}

func (dependencies *productionOAuthFirstLoginDependencies) close() {
	if dependencies == nil {
		return
	}
	for _, provider := range dependencies.providers {
		if provider.client != nil {
			provider.client.CloseIdleConnections()
		}
	}
	dependencies.vault.close()
	dependencies.credentialVault.close()
}

func (dependencies *productionOAuthFirstLoginDependencies) build(
	store *ashrclone.ProductionIdentityStore,
) (map[string]*ashrclone.OAuthFirstLoginService, error) {
	if dependencies == nil || store == nil || dependencies.vault == nil ||
		dependencies.vault.vault == nil || len(dependencies.providers) == 0 {
		return nil, fmt.Errorf("production OAuth first-login dependencies are incomplete")
	}
	firstLoginStore, err := store.NewOAuthFirstLoginStore(dependencies.vault.vault)
	if err != nil {
		return nil, fmt.Errorf("configure production OAuth first-login store: %w", err)
	}
	coordinator, err := ashrclone.NewPostgresOAuthFirstLoginCoordinator(
		ashrclone.PostgresOAuthFirstLoginCoordinatorOptions{
			Store:          store,
			OrganizationID: dependencies.organizationID,
			ProjectID:      dependencies.projectID,
		},
	)
	if err != nil {
		return nil, fmt.Errorf("configure production OAuth first-login coordinator: %w", err)
	}
	services := make(
		map[string]*ashrclone.OAuthFirstLoginService,
		len(dependencies.providers),
	)
	for providerName, provider := range dependencies.providers {
		service, serviceErr := ashrclone.NewOAuthFirstLoginService(
			ashrclone.OAuthFirstLoginServiceOptions{
				Provider:       provider.adapter,
				Credentials:    dependencies.credentials,
				Transactions:   firstLoginStore,
				Secrets:        firstLoginStore,
				Coordinator:    coordinator,
				OrganizationID: dependencies.organizationID,
				ProjectID:      dependencies.projectID,
				CallbackURL:    provider.callbackURL,
				TransactionTTL: provider.transactionTTL,
			},
		)
		if serviceErr != nil {
			return nil, fmt.Errorf(
				"configure production %s OAuth first-login service",
				providerName,
			)
		}
		services[providerName] = service
	}
	return services, nil
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
		return newDevelopmentIdentityRuntime(environment, mode, lookup)
	case ashrclone.IdentityRuntimePostgres:
		dsn := firstEnv(lookup, "ASHR_POSTGRES_DSN", "DATABASE_URL")
		if dsn == "" {
			return identityRuntime{}, fmt.Errorf("production identity requires ASHR_POSTGRES_DSN or DATABASE_URL")
		}
		securityConfig, err := productionIdentitySecurityRuntimeConfigFromEnv(
			lookup,
			dsn,
		)
		if err != nil {
			return identityRuntime{}, err
		}
		store, err := openProductionIdentityStoreFromEnv(dsn, lookup)
		if err != nil {
			return identityRuntime{}, err
		}
		verificationEnabled := envTrue(lookup, "ASHR_IDENTITY_VERIFICATION_ENABLED")
		var deliveryVault *productionIdentityDeliveryVaultRuntime
		var securityRuntime *productionIdentitySecurityRuntime
		oauthDependencies, err := productionOAuthFirstLoginDependenciesFromEnv(lookup)
		if err != nil {
			_ = store.Close()
			return identityRuntime{}, err
		}
		var sessionReceiptTransport ashrclone.IdentitySessionReceiptTransport
		closeResources := func() error {
			deliveryVault.close()
			oauthDependencies.close()
			securityErr := securityRuntime.close()
			storeErr := store.Close()
			if securityErr != nil {
				return securityErr
			}
			return storeErr
		}
		if verificationEnabled {
			deliveryVault, err = productionIdentityDeliveryVaultFromEnv(lookup)
			if err != nil {
				_ = closeResources()
				return identityRuntime{}, err
			}
		}
		if verificationEnabled || oauthDependencies != nil {
			sessionReceiptTransport, err = productionIdentitySessionReceiptTransportFromEnv(lookup)
			if err != nil {
				_ = closeResources()
				return identityRuntime{}, err
			}
		}
		readyCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
		defer cancel()
		if err := store.Ready(readyCtx); err != nil {
			_ = closeResources()
			return identityRuntime{}, err
		}
		tenancy, err := store.NewPostgresTenancyStore()
		if err != nil {
			_ = closeResources()
			return identityRuntime{}, fmt.Errorf(
				"configure production PostgreSQL tenancy store: %w",
				err,
			)
		}
		securityRuntime, err = newProductionIdentitySecurityRuntime(
			ctx,
			securityConfig,
			store,
		)
		if err != nil {
			_ = closeResources()
			return identityRuntime{}, err
		}
		receiptStore, err := store.NewIdentityLifecycleReceiptStore()
		if err != nil {
			_ = closeResources()
			return identityRuntime{}, fmt.Errorf("configure production identity lifecycle receipt store: %w", err)
		}
		coordinator, err := ashrclone.NewPostgresIdentityLifecycleTransactionCoordinator(store, receiptStore)
		if err != nil {
			_ = closeResources()
			return identityRuntime{}, fmt.Errorf("configure production identity lifecycle coordinator: %w", err)
		}
		lifecycle, err := ashrclone.NewIdentityLifecycleService(nil, ashrclone.IdentityLifecycleOptions{
			ReceiptStore:  receiptStore,
			Coordinator:   coordinator,
			Environment:   environment,
			GitHubEnabled: oauthDependencies != nil && oauthDependencies.githubEnabled,
			GoogleEnabled: oauthDependencies != nil && oauthDependencies.googleEnabled,
		})
		if err != nil {
			_ = closeResources()
			return identityRuntime{}, fmt.Errorf("configure production identity lifecycle service: %w", err)
		}
		outbox, err := store.NewOAuthRevocationOutboxStore()
		if err != nil {
			_ = closeResources()
			return identityRuntime{}, err
		}
		oauthFirstLogins := map[string]*ashrclone.OAuthFirstLoginService(nil)
		if oauthDependencies != nil {
			oauthFirstLogins, err = oauthDependencies.build(store)
			if err != nil {
				_ = closeResources()
				return identityRuntime{}, err
			}
		}
		runtime := identityRuntime{
			mode:                    mode,
			identityLifecycle:       lifecycle,
			identitySessions:        store,
			identitySecurityService: nil,
			postgres:                store,
			outbox:                  outbox,
			sessionReceiptTransport: sessionReceiptTransport,
			oauthFirstLogins:        oauthFirstLogins,
			tenancy:                 tenancy,
			close:                   closeResources,
		}
		if securityRuntime != nil {
			runtime.identitySecurityService = securityRuntime.service
		}
		if verificationEnabled {
			digestKey := envRaw(lookup, "ASHR_IDENTITY_VERIFICATION_HMAC_KEY")
			verificationStore, verificationErr := store.NewIdentityVerificationStore(
				ashrclone.PostgresIdentityVerificationStoreOptions{
					OrganizationID: env(lookup, "ASHR_IDENTITY_VERIFICATION_ORGANIZATION_ID"),
					ProjectID:      env(lookup, "ASHR_IDENTITY_VERIFICATION_PROJECT_ID"),
					PrincipalID:    env(lookup, "ASHR_IDENTITY_VERIFICATION_PRINCIPAL_ID"),
					DigestKey:      []byte(digestKey),
				},
			)
			if verificationErr != nil {
				_ = closeResources()
				return identityRuntime{}, fmt.Errorf("configure production identity verification store: %w", verificationErr)
			}
			var coordinator *ashrclone.PostgresIdentityVerificationTransactionCoordinator
			coordinator, coordinatorErr := store.NewIdentityVerificationTransactionCoordinator(verificationStore)
			if coordinatorErr != nil {
				verificationStore.Close()
				_ = closeResources()
				return identityRuntime{}, fmt.Errorf("configure production identity verification transaction coordinator: %w", coordinatorErr)
			}
			verification, verificationErr := ashrclone.NewIdentityVerificationService(
				ashrclone.IdentityVerificationServiceOptions{
					Store:                  verificationStore,
					DeliveryVaultSealer:    deliveryVault.sealer,
					DeliveryVaultDeleter:   deliveryVault.sealer,
					DeliveryMode:           ashrclone.IdentityVerificationDeliveryTransactionalOutbox,
					TransactionCoordinator: coordinator, DigestKey: []byte(digestKey),
				},
			)
			if verificationErr != nil {
				verificationStore.Close()
				_ = closeResources()
				return identityRuntime{}, fmt.Errorf("configure production identity verification service: %w", verificationErr)
			}
			responsePolicy, policyErr := ashrclone.NewIdentityVerificationResponsePolicy(
				ashrclone.IdentityVerificationResponsePolicyOptions{
					Budget: ashrclone.DatabaseEnforcedIdentityVerificationAbuseBudget{},
				},
			)
			if policyErr != nil {
				verification.Close()
				verificationStore.Close()
				_ = closeResources()
				return identityRuntime{}, fmt.Errorf("configure production identity verification response policy: %w", policyErr)
			}
			runtime.verification = verification
			runtime.verificationResponsePolicy = responsePolicy
			runtime.close = func() error {
				verification.Close()
				verificationStore.Close()
				return closeResources()
			}
		}
		return runtime, nil
	default:
		return identityRuntime{}, fmt.Errorf("unsupported ASHR_IDENTITY_RUNTIME %q", mode)
	}
}

func productionOAuthFirstLoginDependenciesFromEnv(
	lookup func(string) (string, bool),
) (*productionOAuthFirstLoginDependencies, error) {
	googleEnabled, err := productionOAuthBooleanEnv(
		lookup,
		"ASHR_GOOGLE_OAUTH_ENABLED",
	)
	if err != nil {
		return nil, err
	}
	githubEnabled, err := productionOAuthBooleanEnv(
		lookup,
		"ASHR_GITHUB_OAUTH_ENABLED",
	)
	if err != nil {
		return nil, err
	}
	for _, key := range []string{
		"ASHR_GOOGLE_OAUTH_DEV_SESSION_ENABLED",
		"ASHR_GITHUB_OAUTH_DEV_SESSION_ENABLED",
	} {
		enabled, flagErr := productionOAuthBooleanEnv(lookup, key)
		if flagErr != nil {
			return nil, flagErr
		}
		if enabled {
			return nil, fmt.Errorf(
				"production OAuth refuses development session configuration",
			)
		}
	}
	if !googleEnabled && !githubEnabled {
		return nil, nil
	}

	organizationID, err := requiredProductionOAuthValue(
		lookup,
		"ASHR_OAUTH_FIRST_LOGIN_ORGANIZATION_ID",
	)
	if err != nil || !validProductionOAuthUUID(organizationID) {
		return nil, fmt.Errorf(
			"ASHR_OAUTH_FIRST_LOGIN_ORGANIZATION_ID must be a canonical UUID",
		)
	}
	projectID, err := requiredProductionOAuthValue(
		lookup,
		"ASHR_OAUTH_FIRST_LOGIN_PROJECT_ID",
	)
	if err != nil || !validProductionOAuthUUID(projectID) {
		return nil, fmt.Errorf(
			"ASHR_OAUTH_FIRST_LOGIN_PROJECT_ID must be a canonical UUID",
		)
	}
	references, err := productionOAuthCredentialReferencesFromEnv(
		lookup, googleEnabled, githubEnabled,
	)
	if err != nil {
		return nil, err
	}
	credentialVault, err := productionOAuthCredentialsRuntimeFactory(
		lookup, googleEnabled, githubEnabled, references,
	)
	if err != nil || credentialVault == nil || credentialVault.provider == nil {
		if err == nil {
			err = fmt.Errorf(
				"production OAuth external credential resolver is incomplete",
			)
		}
		return nil, err
	}
	credentials := credentialVault.provider
	vault, err := productionOAuthOpaqueVaultFromEnv(lookup)
	if err != nil {
		credentialVault.close()
		return nil, err
	}
	dependencies := &productionOAuthFirstLoginDependencies{
		organizationID:  organizationID,
		projectID:       projectID,
		credentials:     credentials,
		credentialVault: credentialVault,
		vault:           vault,
		googleEnabled:   googleEnabled,
		githubEnabled:   githubEnabled,
		providers:       make(map[string]productionOAuthFirstLoginProvider, 2),
	}
	keep := false
	defer func() {
		if !keep {
			dependencies.close()
		}
	}()

	resolvedCredentials := make(map[string]ashrclone.OAuthClientCredentials, 2)
	if googleEnabled {
		resolved, credentialErr := resolveProductionOAuthCredentials(
			credentials, "google",
		)
		if credentialErr != nil {
			return nil, credentialErr
		}
		resolvedCredentials["google"] = resolved
		provider, providerErr := productionGoogleOAuthFirstLoginProvider(
			lookup,
		)
		if providerErr != nil {
			return nil, providerErr
		}
		dependencies.providers["google"] = provider
	}
	if githubEnabled {
		resolved, credentialErr := resolveProductionOAuthCredentials(
			credentials, "github",
		)
		if credentialErr != nil {
			return nil, credentialErr
		}
		resolvedCredentials["github"] = resolved
		provider, providerErr := productionGitHubOAuthFirstLoginProvider(
			lookup,
		)
		if providerErr != nil {
			return nil, providerErr
		}
		dependencies.providers["github"] = provider
	}
	if googleEnabled && githubEnabled {
		googleCredentials := resolvedCredentials["google"]
		githubCredentials := resolvedCredentials["github"]
		if googleCredentials.ClientID == githubCredentials.ClientID ||
			googleCredentials.ClientSecret == githubCredentials.ClientSecret {
			return nil, fmt.Errorf(
				"production OAuth providers must not share client material",
			)
		}
	}
	keep = true
	return dependencies, nil
}

func productionGoogleOAuthFirstLoginProvider(
	lookup func(string) (string, bool),
) (productionOAuthFirstLoginProvider, error) {
	callbackURL, err := productionOAuthCallbackURLFromEnv(
		lookup,
		"google",
	)
	if err != nil {
		return productionOAuthFirstLoginProvider{}, err
	}
	transactionTTL, err := productionOAuthDurationSeconds(
		lookup,
		"ASHR_GOOGLE_OAUTH_TRANSACTION_TTL_SECONDS",
		productionOAuthFirstLoginDefaultTTL,
		30,
		30*60,
	)
	if err != nil {
		return productionOAuthFirstLoginProvider{}, err
	}
	upstreamTimeout, err := productionOAuthDurationSeconds(
		lookup,
		"ASHR_GOOGLE_OAUTH_UPSTREAM_TIMEOUT_SECONDS",
		productionOAuthProviderDefaultTimeout,
		1,
		60,
	)
	if err != nil {
		return productionOAuthFirstLoginProvider{}, err
	}
	client := newProductionOAuthProviderHTTPClient(upstreamTimeout)
	provider, err := ashrclone.NewGoogleOIDCProvider(
		ashrclone.GoogleOIDCOptions{
			HTTPClient:      client,
			AuthorizeURL:    env(lookup, "ASHR_GOOGLE_OAUTH_AUTHORIZE_URL"),
			TokenURL:        env(lookup, "ASHR_GOOGLE_OAUTH_TOKEN_URL"),
			RevokeURL:       env(lookup, "ASHR_GOOGLE_OAUTH_REVOKE_URL"),
			JWKSURL:         env(lookup, "ASHR_GOOGLE_OAUTH_JWKS_URL"),
			UpstreamTimeout: upstreamTimeout,
		},
	)
	if err != nil {
		client.CloseIdleConnections()
		return productionOAuthFirstLoginProvider{}, fmt.Errorf(
			"production Google OAuth provider configuration was rejected",
		)
	}
	return productionOAuthFirstLoginProvider{
		adapter: provider, callbackURL: callbackURL,
		transactionTTL: transactionTTL, client: client,
	}, nil
}

func productionGitHubOAuthFirstLoginProvider(
	lookup func(string) (string, bool),
) (productionOAuthFirstLoginProvider, error) {
	callbackURL, err := productionOAuthCallbackURLFromEnv(
		lookup,
		"github",
	)
	if err != nil {
		return productionOAuthFirstLoginProvider{}, err
	}
	transactionTTL, err := productionOAuthDurationSeconds(
		lookup,
		"ASHR_GITHUB_OAUTH_TRANSACTION_TTL_SECONDS",
		productionOAuthFirstLoginDefaultTTL,
		30,
		30*60,
	)
	if err != nil {
		return productionOAuthFirstLoginProvider{}, err
	}
	upstreamTimeout, err := productionOAuthDurationSeconds(
		lookup,
		"ASHR_GITHUB_OAUTH_UPSTREAM_TIMEOUT_SECONDS",
		productionOAuthProviderDefaultTimeout,
		1,
		60,
	)
	if err != nil {
		return productionOAuthFirstLoginProvider{}, err
	}
	client := newProductionOAuthProviderHTTPClient(upstreamTimeout)
	provider, err := ashrclone.NewGitHubOAuthProvider(
		ashrclone.GitHubOAuthProviderOptions{
			HTTPClient:      client,
			AuthorizeURL:    env(lookup, "ASHR_GITHUB_OAUTH_AUTHORIZE_URL"),
			TokenURL:        env(lookup, "ASHR_GITHUB_OAUTH_TOKEN_URL"),
			APIURL:          env(lookup, "ASHR_GITHUB_OAUTH_API_URL"),
			UpstreamTimeout: upstreamTimeout,
		},
	)
	if err != nil {
		client.CloseIdleConnections()
		return productionOAuthFirstLoginProvider{}, fmt.Errorf(
			"production GitHub OAuth provider configuration was rejected",
		)
	}
	return productionOAuthFirstLoginProvider{
		adapter: provider, callbackURL: callbackURL,
		transactionTTL: transactionTTL, client: client,
	}, nil
}

var productionOAuthCredentialsRuntimeFactory = productionOAuthCredentialsRuntimeFromEnv

func productionOAuthCredentialReferencesFromEnv(
	lookup func(string) (string, bool),
	googleEnabled bool,
	githubEnabled bool,
) (map[string]ashrclone.OAuthCredentialReference, error) {
	if lookup == nil {
		return nil, fmt.Errorf("identity environment lookup is required")
	}
	enabled := map[string]bool{"google": googleEnabled, "github": githubEnabled}
	references := make(map[string]ashrclone.OAuthCredentialReference, 2)
	seen := make(map[string]string, 4)
	for _, provider := range []string{"google", "github"} {
		if !enabled[provider] {
			continue
		}
		upper := strings.ToUpper(provider)
		for _, suffix := range []string{"CLIENT_ID", "CLIENT_SECRET"} {
			if value, present := lookup("ASHR_" + upper + "_OAUTH_" + suffix); present {
				if strings.TrimSpace(value) != "" ||
					value != strings.TrimSpace(value) ||
					strings.ContainsAny(value, "\x00\r\n\t") {
					return nil, fmt.Errorf(
						"production %s OAuth credentials must be delivered by the external secret manager",
						provider,
					)
				}
				return nil, fmt.Errorf(
					"production %s OAuth credential environment variables are forbidden",
					provider,
				)
			}
		}
		clientIDRef, err := requiredProductionOAuthValue(
			lookup, "ASHR_"+upper+"_OAUTH_CLIENT_ID_REF",
		)
		if err != nil || !ashrclone.ValidOAuthCredentialReference(clientIDRef) {
			return nil, fmt.Errorf(
				"production %s OAuth client ID reference is invalid",
				provider,
			)
		}
		clientSecretRef, err := requiredProductionOAuthValue(
			lookup, "ASHR_"+upper+"_OAUTH_CLIENT_SECRET_REF",
		)
		if err != nil || !ashrclone.ValidOAuthCredentialReference(clientSecretRef) ||
			clientIDRef == clientSecretRef {
			return nil, fmt.Errorf(
				"production %s OAuth client secret reference is invalid",
				provider,
			)
		}
		for kind, reference := range map[string]string{
			"client_id": clientIDRef, "client_secret": clientSecretRef,
		} {
			if _, exists := seen[reference]; exists {
				return nil, fmt.Errorf(
					"production OAuth credential references must be unique",
				)
			}
			seen[reference] = provider + "." + kind
		}
		references[provider] = ashrclone.OAuthCredentialReference{
			ClientIDRef: clientIDRef, ClientSecretRef: clientSecretRef,
		}
	}
	return references, nil
}

func productionOAuthCredentialsRuntimeFromEnv(
	lookup func(string) (string, bool),
	googleEnabled bool,
	githubEnabled bool,
	references map[string]ashrclone.OAuthCredentialReference,
) (*productionOAuthCredentialsRuntime, error) {
	if lookup == nil || len(references) == 0 {
		return nil, fmt.Errorf(
			"production OAuth external credential resolver is required",
		)
	}
	type binding struct {
		key         string
		destination *string
	}
	var endpoint, caBundleFile, clientCertificateFile, clientPrivateKeyFile, serverName string
	bindings := []binding{
		{"ASHR_OAUTH_CREDENTIALS_RESOLVE_URL", &endpoint},
		{"ASHR_OAUTH_CREDENTIALS_MTLS_CA_FILE", &caBundleFile},
		{"ASHR_OAUTH_CREDENTIALS_MTLS_CLIENT_CERT_FILE", &clientCertificateFile},
		{"ASHR_OAUTH_CREDENTIALS_MTLS_CLIENT_KEY_FILE", &clientPrivateKeyFile},
		{"ASHR_OAUTH_CREDENTIALS_MTLS_SERVER_NAME", &serverName},
	}
	missing := make([]string, 0, len(bindings))
	for _, item := range bindings {
		value, present := lookup(item.key)
		if !present || strings.TrimSpace(value) == "" {
			missing = append(missing, item.key)
			continue
		}
		if value != strings.TrimSpace(value) ||
			strings.ContainsAny(value, "\x00\r\n\t") {
			return nil, fmt.Errorf(
				"production OAuth external credential resolver configuration is invalid",
			)
		}
		*item.destination = value
	}
	if len(missing) != 0 {
		return nil, fmt.Errorf(
			"production OAuth external credential resolver configuration is incomplete",
		)
	}
	if !googleEnabled && !githubEnabled {
		return nil, fmt.Errorf(
			"production OAuth external credential resolver has no enabled provider",
		)
	}
	caBundlePEM, err := readProductionIdentityDeliveryVaultPEM(
		caBundleFile, maxProductionIdentityDeliveryVaultCABundleBytes,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"production OAuth credential resolver mTLS trust material is unavailable",
		)
	}
	defer zeroBytes(caBundlePEM)
	clientCertificatePEM, err := readProductionIdentityDeliveryVaultPEM(
		clientCertificateFile, maxProductionIdentityDeliveryVaultIdentityBytes,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"production OAuth credential resolver mTLS identity material is unavailable",
		)
	}
	defer zeroBytes(clientCertificatePEM)
	clientPrivateKeyPEM, err := readProductionIdentityDeliveryVaultPEM(
		clientPrivateKeyFile, maxProductionIdentityDeliveryVaultIdentityBytes,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"production OAuth credential resolver mTLS identity material is unavailable",
		)
	}
	defer zeroBytes(clientPrivateKeyPEM)
	client, err := ashrclone.NewIdentityDeliveryMTLSHTTPClient(
		ashrclone.IdentityDeliveryMTLSClientOptions{
			CABundlePEM: caBundlePEM, ClientCertificatePEM: clientCertificatePEM,
			ClientPrivateKeyPEM: clientPrivateKeyPEM, ServerName: serverName,
			DialTimeout:           productionIdentityDeliveryVaultConnectTimeout,
			TLSHandshakeTimeout:   productionIdentityDeliveryVaultConnectTimeout,
			ResponseHeaderTimeout: productionIdentityDeliveryVaultRequestTimeout,
			RequestTimeout:        productionIdentityDeliveryVaultRequestTimeout,
		},
	)
	if err != nil {
		return nil, fmt.Errorf(
			"production OAuth credential resolver mTLS profile was rejected",
		)
	}
	provider, err := ashrclone.NewHTTPOAuthCredentialsProvider(
		ashrclone.HTTPOAuthCredentialsProviderOptions{
			Endpoint: endpoint, Client: client,
			Timeout:    productionIdentityDeliveryVaultRequestTimeout,
			References: references,
		},
	)
	if err != nil {
		client.CloseIdleConnections()
		return nil, fmt.Errorf(
			"production OAuth credential resolver endpoints were rejected",
		)
	}
	return &productionOAuthCredentialsRuntime{
		provider: provider, client: client,
	}, nil
}

func resolveProductionOAuthCredentials(
	credentials ashrclone.OAuthCredentialsProvider,
	provider string,
) (ashrclone.OAuthClientCredentials, error) {
	if credentials == nil {
		return ashrclone.OAuthClientCredentials{}, fmt.Errorf(
			"production %s OAuth credentials are unavailable", provider,
		)
	}
	resolved, err := credentials.OAuthCredentials(context.Background(), provider)
	if err != nil ||
		!validProductionOAuthClientMaterial(resolved.ClientID, 4096) ||
		!validProductionOAuthClientMaterial(resolved.ClientSecret, 16384) ||
		resolved.ClientID == resolved.ClientSecret {
		return ashrclone.OAuthClientCredentials{}, fmt.Errorf(
			"production %s OAuth credentials are unavailable", provider,
		)
	}
	return resolved, nil
}

func validProductionOAuthClientMaterial(value string, maximum int) bool {
	return value != "" && value == strings.TrimSpace(value) &&
		len(value) <= maximum && !strings.ContainsAny(value, "\x00\r\n\t")
}

func productionOAuthOpaqueVaultFromEnv(
	lookup func(string) (string, bool),
) (*productionOAuthOpaqueVaultRuntime, error) {
	config, err := productionOAuthOpaqueVaultConfigFromEnv(lookup)
	if err != nil {
		return nil, err
	}
	caBundlePEM, err := readProductionIdentityDeliveryVaultPEM(
		config.caBundleFile,
		maxProductionIdentityDeliveryVaultCABundleBytes,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"production OAuth opaque vault mTLS trust material is unavailable",
		)
	}
	defer zeroBytes(caBundlePEM)
	clientCertificatePEM, err := readProductionIdentityDeliveryVaultPEM(
		config.clientCertificateFile,
		maxProductionIdentityDeliveryVaultIdentityBytes,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"production OAuth opaque vault mTLS identity material is unavailable",
		)
	}
	defer zeroBytes(clientCertificatePEM)
	clientPrivateKeyPEM, err := readProductionIdentityDeliveryVaultPEM(
		config.clientPrivateKeyFile,
		maxProductionIdentityDeliveryVaultIdentityBytes,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"production OAuth opaque vault mTLS identity material is unavailable",
		)
	}
	defer zeroBytes(clientPrivateKeyPEM)
	client, err := ashrclone.NewIdentityDeliveryMTLSHTTPClient(
		ashrclone.IdentityDeliveryMTLSClientOptions{
			CABundlePEM:           caBundlePEM,
			ClientCertificatePEM:  clientCertificatePEM,
			ClientPrivateKeyPEM:   clientPrivateKeyPEM,
			ServerName:            config.serverName,
			DialTimeout:           productionIdentityDeliveryVaultConnectTimeout,
			TLSHandshakeTimeout:   productionIdentityDeliveryVaultConnectTimeout,
			ResponseHeaderTimeout: productionIdentityDeliveryVaultRequestTimeout,
			RequestTimeout:        productionIdentityDeliveryVaultRequestTimeout,
		},
	)
	if err != nil {
		return nil, fmt.Errorf(
			"production OAuth opaque vault mTLS profile was rejected",
		)
	}
	vault, err := ashrclone.NewHTTPOAuthOpaqueVault(
		ashrclone.HTTPOAuthOpaqueVaultOptions{
			PutEndpoint:     config.putURL,
			GetEndpoint:     config.getURL,
			BindingEndpoint: config.bindingURL,
			DeleteEndpoint:  config.deleteURL,
			Client:          client,
			Timeout:         productionIdentityDeliveryVaultRequestTimeout,
		},
	)
	if err != nil {
		client.CloseIdleConnections()
		return nil, fmt.Errorf(
			"production OAuth opaque vault endpoints were rejected",
		)
	}
	return &productionOAuthOpaqueVaultRuntime{vault: vault, client: client}, nil
}

func productionOAuthOpaqueVaultConfigFromEnv(
	lookup func(string) (string, bool),
) (productionOAuthOpaqueVaultConfig, error) {
	if lookup == nil {
		return productionOAuthOpaqueVaultConfig{}, fmt.Errorf(
			"identity environment lookup is required",
		)
	}
	var config productionOAuthOpaqueVaultConfig
	bindings := []struct {
		key         string
		destination *string
	}{
		{"ASHR_OAUTH_VAULT_PUT_URL", &config.putURL},
		{"ASHR_OAUTH_VAULT_GET_URL", &config.getURL},
		{"ASHR_OAUTH_VAULT_BINDING_URL", &config.bindingURL},
		{"ASHR_OAUTH_VAULT_DELETE_URL", &config.deleteURL},
		{"ASHR_OAUTH_VAULT_MTLS_CA_FILE", &config.caBundleFile},
		{"ASHR_OAUTH_VAULT_MTLS_CLIENT_CERT_FILE", &config.clientCertificateFile},
		{"ASHR_OAUTH_VAULT_MTLS_CLIENT_KEY_FILE", &config.clientPrivateKeyFile},
		{"ASHR_OAUTH_VAULT_MTLS_SERVER_NAME", &config.serverName},
	}
	missing := make([]string, 0, len(bindings))
	for _, binding := range bindings {
		value, present := lookup(binding.key)
		if !present || strings.TrimSpace(value) == "" {
			missing = append(missing, binding.key)
			continue
		}
		if value != strings.TrimSpace(value) ||
			strings.ContainsAny(value, "\x00\r\n\t") {
			return productionOAuthOpaqueVaultConfig{}, fmt.Errorf(
				"production OAuth opaque vault configuration is invalid",
			)
		}
		*binding.destination = value
	}
	if len(missing) != 0 {
		return productionOAuthOpaqueVaultConfig{}, fmt.Errorf(
			"production OAuth opaque vault configuration must be all-or-none; missing %s",
			strings.Join(missing, ", "),
		)
	}
	return config, nil
}

func productionOAuthCallbackURLFromEnv(
	lookup func(string) (string, bool),
	provider string,
) (string, error) {
	key := "ASHR_" + strings.ToUpper(provider) + "_OAUTH_CALLBACK_URL"
	raw, err := requiredProductionOAuthValue(lookup, key)
	if err != nil {
		return "", err
	}
	callback, err := url.ParseRequestURI(raw)
	if err != nil || callback.Scheme != "https" || callback.Host == "" ||
		callback.User != nil || callback.RawQuery != "" ||
		callback.Fragment != "" ||
		callback.Path != "/v1/identity/oauth/"+provider+"/callback" {
		return "", fmt.Errorf(
			"%s must be the dedicated absolute HTTPS provider callback",
			key,
		)
	}
	return callback.String(), nil
}

func validateProductionOAuthCredentials(
	credentials ashrclone.OAuthCredentialsProvider,
	provider string,
) error {
	_, err := resolveProductionOAuthCredentials(credentials, provider)
	return err
}

func requiredProductionOAuthValue(
	lookup func(string) (string, bool),
	key string,
) (string, error) {
	if lookup == nil {
		return "", fmt.Errorf("identity environment lookup is required")
	}
	value, present := lookup(key)
	if !present || value == "" || value != strings.TrimSpace(value) ||
		strings.ContainsAny(value, "\x00\r\n\t") {
		return "", fmt.Errorf("%s is required", key)
	}
	return value, nil
}

func productionOAuthBooleanEnv(
	lookup func(string) (string, bool),
	key string,
) (bool, error) {
	if lookup == nil {
		return false, fmt.Errorf("identity environment lookup is required")
	}
	raw, present := lookup(key)
	if !present || strings.TrimSpace(raw) == "" {
		return false, nil
	}
	if raw != strings.TrimSpace(raw) || strings.ContainsAny(raw, "\x00\r\n\t") {
		return false, fmt.Errorf("%s must be a boolean", key)
	}
	value, err := strconv.ParseBool(raw)
	if err != nil {
		return false, fmt.Errorf("%s must be a boolean", key)
	}
	return value, nil
}

func productionOAuthDurationSeconds(
	lookup func(string) (string, bool),
	key string,
	fallback time.Duration,
	minimum int,
	maximum int,
) (time.Duration, error) {
	raw := env(lookup, key)
	if raw == "" {
		return fallback, nil
	}
	seconds, err := strconv.Atoi(raw)
	if err != nil || seconds < minimum || seconds > maximum {
		return 0, fmt.Errorf(
			"%s must be between %d and %d",
			key,
			minimum,
			maximum,
		)
	}
	return time.Duration(seconds) * time.Second, nil
}

func validProductionOAuthUUID(value string) bool {
	if len(value) != 36 {
		return false
	}
	for index := 0; index < len(value); index++ {
		if index == 8 || index == 13 || index == 18 || index == 23 {
			if value[index] != '-' {
				return false
			}
			continue
		}
		character := value[index]
		if (character < '0' || character > '9') &&
			(character < 'a' || character > 'f') {
			return false
		}
	}
	return true
}

func newProductionOAuthProviderHTTPClient(timeout time.Duration) *http.Client {
	return &http.Client{
		Timeout: timeout,
		CheckRedirect: func(*http.Request, []*http.Request) error {
			return fmt.Errorf("production OAuth provider redirect refused")
		},
	}
}

func productionIdentityDeliveryVaultFromEnv(
	lookup func(string) (string, bool),
) (*productionIdentityDeliveryVaultRuntime, error) {
	config, err := productionIdentityDeliveryVaultConfigFromEnv(lookup)
	if err != nil {
		return nil, err
	}
	caBundlePEM, err := readProductionIdentityDeliveryVaultPEM(
		config.caBundleFile,
		maxProductionIdentityDeliveryVaultCABundleBytes,
	)
	if err != nil {
		return nil, fmt.Errorf("production identity delivery vault mTLS trust material is unavailable")
	}
	defer zeroBytes(caBundlePEM)
	clientCertificatePEM, err := readProductionIdentityDeliveryVaultPEM(
		config.clientCertificateFile,
		maxProductionIdentityDeliveryVaultIdentityBytes,
	)
	if err != nil {
		return nil, fmt.Errorf("production identity delivery vault mTLS identity material is unavailable")
	}
	defer zeroBytes(clientCertificatePEM)
	clientPrivateKeyPEM, err := readProductionIdentityDeliveryVaultPEM(
		config.clientPrivateKeyFile,
		maxProductionIdentityDeliveryVaultIdentityBytes,
	)
	if err != nil {
		return nil, fmt.Errorf("production identity delivery vault mTLS identity material is unavailable")
	}
	defer zeroBytes(clientPrivateKeyPEM)

	client, err := ashrclone.NewIdentityDeliveryMTLSHTTPClient(
		ashrclone.IdentityDeliveryMTLSClientOptions{
			CABundlePEM:           caBundlePEM,
			ClientCertificatePEM:  clientCertificatePEM,
			ClientPrivateKeyPEM:   clientPrivateKeyPEM,
			ServerName:            config.serverName,
			DialTimeout:           productionIdentityDeliveryVaultConnectTimeout,
			TLSHandshakeTimeout:   productionIdentityDeliveryVaultConnectTimeout,
			ResponseHeaderTimeout: productionIdentityDeliveryVaultRequestTimeout,
			RequestTimeout:        productionIdentityDeliveryVaultRequestTimeout,
		},
	)
	if err != nil {
		return nil, fmt.Errorf("production identity delivery vault mTLS profile was rejected")
	}
	sealer, err := ashrclone.NewHTTPIdentityDeliveryVaultSealer(
		ashrclone.HTTPIdentityDeliveryVaultSealerOptions{
			SealEndpoint:   config.sealURL,
			DeleteEndpoint: config.deleteURL,
			Client:         client,
			Timeout:        productionIdentityDeliveryVaultRequestTimeout,
		},
	)
	if err != nil {
		client.CloseIdleConnections()
		return nil, fmt.Errorf("production identity delivery vault endpoints were rejected")
	}
	return &productionIdentityDeliveryVaultRuntime{
		sealer: sealer,
		client: client,
	}, nil
}

func productionIdentityDeliveryVaultConfigFromEnv(
	lookup func(string) (string, bool),
) (productionIdentityDeliveryVaultConfig, error) {
	if lookup == nil {
		return productionIdentityDeliveryVaultConfig{}, fmt.Errorf("identity environment lookup is required")
	}
	var config productionIdentityDeliveryVaultConfig
	bindings := []struct {
		key         string
		destination *string
	}{
		{"ASHR_IDENTITY_DELIVERY_VAULT_SEAL_URL", &config.sealURL},
		{"ASHR_IDENTITY_DELIVERY_VAULT_DELETE_URL", &config.deleteURL},
		{"ASHR_IDENTITY_DELIVERY_VAULT_MTLS_CA_FILE", &config.caBundleFile},
		{"ASHR_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_CERT_FILE", &config.clientCertificateFile},
		{"ASHR_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_KEY_FILE", &config.clientPrivateKeyFile},
		{"ASHR_IDENTITY_DELIVERY_VAULT_MTLS_SERVER_NAME", &config.serverName},
	}
	missing := make([]string, 0, len(bindings))
	for _, binding := range bindings {
		value, present := lookup(binding.key)
		if !present || strings.TrimSpace(value) == "" {
			missing = append(missing, binding.key)
			continue
		}
		*binding.destination = value
	}
	if len(missing) != 0 {
		return productionIdentityDeliveryVaultConfig{}, fmt.Errorf(
			"production identity delivery vault configuration must be all-or-none; missing %s",
			strings.Join(missing, ", "),
		)
	}
	for _, binding := range bindings {
		value := *binding.destination
		if value != strings.TrimSpace(value) || strings.ContainsAny(value, "\x00\r\n") {
			return productionIdentityDeliveryVaultConfig{}, fmt.Errorf(
				"production identity delivery vault configuration is invalid",
			)
		}
	}
	return config, nil
}

func readProductionIdentityDeliveryVaultPEM(path string, limit int64) ([]byte, error) {
	if path == "" || path != strings.TrimSpace(path) ||
		strings.ContainsAny(path, "\x00\r\n") || limit < 1 {
		return nil, fmt.Errorf("production identity delivery vault credential file is invalid")
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("production identity delivery vault credential file is unavailable")
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Size() < 1 || info.Size() > limit {
		return nil, fmt.Errorf("production identity delivery vault credential file is invalid")
	}
	encoded, err := io.ReadAll(io.LimitReader(file, limit+1))
	if err != nil || len(encoded) == 0 || int64(len(encoded)) > limit ||
		int64(len(encoded)) != info.Size() {
		zeroBytes(encoded)
		return nil, fmt.Errorf("production identity delivery vault credential file is invalid")
	}
	return encoded, nil
}

func openProductionIdentityStoreFromEnv(
	dsn string,
	lookup func(string) (string, bool),
) (*ashrclone.ProductionIdentityStore, error) {
	config, err := identitySessionHMACRuntimeConfigFromEnv(lookup)
	if err != nil {
		return nil, err
	}
	defer config.clear()
	lifecycle, err := identityLifecycleKeyRuntimeConfigFromEnv(lookup)
	if err != nil {
		return nil, err
	}
	defer lifecycle.clear()
	db, err := openIdentityDatabase("postgres", dsn)
	if err != nil {
		return nil, fmt.Errorf("open production identity postgres: invalid database configuration")
	}
	store, err := ashrclone.NewProductionIdentityStore(ashrclone.ProductionIdentityStoreOptions{
		DB:                                 db,
		SessionKey:                         config.activeKey,
		SessionKeyVersion:                  config.activeVersion,
		PreviousSessionKeys:                config.previousKeys,
		LegacySessionKeyVersion:            config.legacyVersion,
		RequirePreviousKeyRetention:        true,
		LifecycleReceiptKey:                lifecycle.activeKey,
		LifecycleReceiptKeyVersion:         lifecycle.activeVersion,
		PreviousLifecycleReceiptKeys:       lifecycle.previousKeys,
		LifecycleReceiptLookupKey:          lifecycle.lookupActiveKey,
		LifecycleReceiptLookupKeyVersion:   lifecycle.lookupActiveVersion,
		PreviousLifecycleReceiptLookupKeys: lifecycle.previousLookupKeys,
	})
	if err != nil {
		_ = db.Close()
		return nil, err
	}
	return store, nil
}

func identityLifecycleKeyRuntimeConfigFromEnv(
	lookup func(string) (string, bool),
) (identityLifecycleKeyRuntimeConfig, error) {
	config := identityLifecycleKeyRuntimeConfig{}
	keep := false
	defer func() {
		if !keep {
			config.clear()
		}
	}()

	activeVersion := env(lookup, "ASHR_IDENTITY_LIFECYCLE_RECEIPT_ACTIVE_VERSION")
	activeKey := envRaw(lookup, "ASHR_IDENTITY_LIFECYCLE_RECEIPT_KEY")
	missing := make([]string, 0, 2)
	if activeVersion == "" {
		missing = append(missing, "ASHR_IDENTITY_LIFECYCLE_RECEIPT_ACTIVE_VERSION")
	}
	if activeKey == "" {
		missing = append(missing, "ASHR_IDENTITY_LIFECYCLE_RECEIPT_KEY")
	}
	if len(missing) != 0 {
		return identityLifecycleKeyRuntimeConfig{}, fmt.Errorf(
			"production identity lifecycle keyring requires %s", strings.Join(missing, ", "),
		)
	}
	if !validIdentitySessionKeyVersion(activeVersion) {
		return identityLifecycleKeyRuntimeConfig{}, fmt.Errorf("production identity lifecycle keyring contains an invalid version")
	}
	if len(activeKey) < 32 {
		return identityLifecycleKeyRuntimeConfig{}, fmt.Errorf("ASHR_IDENTITY_LIFECYCLE_RECEIPT_KEY must contain at least 32 bytes")
	}
	entries, err := decodeIdentityLifecyclePreviousKeys(
		envRaw(lookup, "ASHR_IDENTITY_LIFECYCLE_RECEIPT_PREVIOUS_KEYS_JSON"),
		"ASHR_IDENTITY_LIFECYCLE_RECEIPT_PREVIOUS_KEYS_JSON",
	)
	if err != nil {
		return identityLifecycleKeyRuntimeConfig{}, err
	}
	defer func() {
		for index := range entries {
			entries[index].Key = ""
		}
	}()
	config.activeVersion = activeVersion
	config.activeKey = []byte(activeKey)
	versions := map[string]struct{}{activeVersion: {}}
	config.previousKeys = make([]ashrclone.IdentityLifecycleEncryptionKey, 0, len(entries))
	for index, entry := range entries {
		version := strings.TrimSpace(entry.Version)
		if !validIdentitySessionKeyVersion(version) {
			return identityLifecycleKeyRuntimeConfig{}, fmt.Errorf(
				"ASHR_IDENTITY_LIFECYCLE_RECEIPT_PREVIOUS_KEYS_JSON entry %d has an invalid version", index,
			)
		}
		if len(entry.Key) < 32 {
			return identityLifecycleKeyRuntimeConfig{}, fmt.Errorf(
				"ASHR_IDENTITY_LIFECYCLE_RECEIPT_PREVIOUS_KEYS_JSON entry %d has a key shorter than 32 bytes", index,
			)
		}
		if _, duplicate := versions[version]; duplicate {
			return identityLifecycleKeyRuntimeConfig{}, fmt.Errorf(
				"ASHR_IDENTITY_LIFECYCLE_RECEIPT_PREVIOUS_KEYS_JSON entry %d duplicates a key version", index,
			)
		}
		versions[version] = struct{}{}
		config.previousKeys = append(config.previousKeys, ashrclone.IdentityLifecycleEncryptionKey{
			Version: version, Key: []byte(entry.Key),
		})
	}
	lookupActiveVersion := env(
		lookup, "ASHR_IDENTITY_LIFECYCLE_RECEIPT_LOOKUP_ACTIVE_VERSION",
	)
	lookupActiveKey := envRaw(
		lookup, "ASHR_IDENTITY_LIFECYCLE_RECEIPT_LOOKUP_KEY",
	)
	lookupPreviousRaw := envRaw(
		lookup, "ASHR_IDENTITY_LIFECYCLE_RECEIPT_LOOKUP_PREVIOUS_KEYS_JSON",
	)
	if (lookupActiveVersion == "") != (lookupActiveKey == "") ||
		(lookupActiveVersion == "" && strings.TrimSpace(lookupPreviousRaw) != "") {
		return identityLifecycleKeyRuntimeConfig{}, fmt.Errorf(
			"production identity lifecycle lookup keyring requires active version and key together",
		)
	}
	if lookupActiveVersion != "" {
		if !validIdentitySessionKeyVersion(lookupActiveVersion) {
			return identityLifecycleKeyRuntimeConfig{}, fmt.Errorf(
				"production identity lifecycle lookup keyring contains an invalid version",
			)
		}
		if len(lookupActiveKey) < 32 {
			return identityLifecycleKeyRuntimeConfig{}, fmt.Errorf(
				"ASHR_IDENTITY_LIFECYCLE_RECEIPT_LOOKUP_KEY must contain at least 32 bytes",
			)
		}
		lookupEntries, lookupErr := decodeIdentityLifecyclePreviousKeys(
			lookupPreviousRaw,
			"ASHR_IDENTITY_LIFECYCLE_RECEIPT_LOOKUP_PREVIOUS_KEYS_JSON",
		)
		if lookupErr != nil {
			return identityLifecycleKeyRuntimeConfig{}, lookupErr
		}
		defer func() {
			for index := range lookupEntries {
				lookupEntries[index].Key = ""
			}
		}()
		config.lookupActiveVersion = lookupActiveVersion
		config.lookupActiveKey = []byte(lookupActiveKey)
		lookupVersions := map[string]struct{}{lookupActiveVersion: {}}
		config.previousLookupKeys = make(
			[]ashrclone.IdentityLifecycleLookupKey, 0, len(lookupEntries),
		)
		for index, entry := range lookupEntries {
			version := strings.TrimSpace(entry.Version)
			if !validIdentitySessionKeyVersion(version) {
				return identityLifecycleKeyRuntimeConfig{}, fmt.Errorf(
					"ASHR_IDENTITY_LIFECYCLE_RECEIPT_LOOKUP_PREVIOUS_KEYS_JSON entry %d has an invalid version", index,
				)
			}
			if len(entry.Key) < 32 {
				return identityLifecycleKeyRuntimeConfig{}, fmt.Errorf(
					"ASHR_IDENTITY_LIFECYCLE_RECEIPT_LOOKUP_PREVIOUS_KEYS_JSON entry %d has a key shorter than 32 bytes", index,
				)
			}
			if _, duplicate := lookupVersions[version]; duplicate {
				return identityLifecycleKeyRuntimeConfig{}, fmt.Errorf(
					"ASHR_IDENTITY_LIFECYCLE_RECEIPT_LOOKUP_PREVIOUS_KEYS_JSON entry %d duplicates a key version", index,
				)
			}
			lookupVersions[version] = struct{}{}
			config.previousLookupKeys = append(config.previousLookupKeys, ashrclone.IdentityLifecycleLookupKey{
				Version: version, Key: []byte(entry.Key),
			})
		}
	}
	keep = true
	return config, nil
}

func decodeIdentityLifecyclePreviousKeys(
	raw string,
	environmentName string,
) ([]identityLifecyclePreviousKeyEnv, error) {
	if strings.TrimSpace(raw) == "" {
		return []identityLifecyclePreviousKeyEnv{}, nil
	}
	decoder := json.NewDecoder(strings.NewReader(raw))
	decoder.DisallowUnknownFields()
	var entries []identityLifecyclePreviousKeyEnv
	if err := decoder.Decode(&entries); err != nil || entries == nil {
		return nil, fmt.Errorf("%s must be a JSON array of version and key objects", environmentName)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return nil, fmt.Errorf("%s must contain exactly one JSON array", environmentName)
	}
	return entries, nil
}

func (config *identityLifecycleKeyRuntimeConfig) clear() {
	if config == nil {
		return
	}
	zeroBytes(config.activeKey)
	for index := range config.previousKeys {
		zeroBytes(config.previousKeys[index].Key)
	}
	zeroBytes(config.lookupActiveKey)
	for index := range config.previousLookupKeys {
		zeroBytes(config.previousLookupKeys[index].Key)
	}
	config.activeKey = nil
	config.previousKeys = nil
	config.activeVersion = ""
	config.lookupActiveKey = nil
	config.previousLookupKeys = nil
	config.lookupActiveVersion = ""
}

func identitySessionHMACRuntimeConfigFromEnv(
	lookup func(string) (string, bool),
) (identitySessionHMACRuntimeConfig, error) {
	activeVersion := env(lookup, "ASHR_IDENTITY_SESSION_HMAC_ACTIVE_VERSION")
	activeKey := envRaw(lookup, "ASHR_IDENTITY_SESSION_HMAC_KEY")
	legacyVersion := env(lookup, "ASHR_IDENTITY_SESSION_HMAC_LEGACY_VERSION")
	missing := make([]string, 0, 3)
	if activeVersion == "" {
		missing = append(missing, "ASHR_IDENTITY_SESSION_HMAC_ACTIVE_VERSION")
	}
	if activeKey == "" {
		missing = append(missing, "ASHR_IDENTITY_SESSION_HMAC_KEY")
	}
	if legacyVersion == "" {
		missing = append(missing, "ASHR_IDENTITY_SESSION_HMAC_LEGACY_VERSION")
	}
	if len(missing) != 0 {
		return identitySessionHMACRuntimeConfig{}, fmt.Errorf(
			"production identity session keyring requires %s",
			strings.Join(missing, ", "),
		)
	}
	if !validIdentitySessionKeyVersion(activeVersion) ||
		!validIdentitySessionKeyVersion(legacyVersion) {
		return identitySessionHMACRuntimeConfig{}, fmt.Errorf("production identity session keyring contains an invalid version")
	}
	if len(activeKey) < 32 {
		return identitySessionHMACRuntimeConfig{}, fmt.Errorf("ASHR_IDENTITY_SESSION_HMAC_KEY must contain at least 32 bytes")
	}
	previousEntries, err := decodeIdentitySessionPreviousKeys(
		envRaw(lookup, "ASHR_IDENTITY_SESSION_HMAC_PREVIOUS_KEYS_JSON"),
	)
	if err != nil {
		return identitySessionHMACRuntimeConfig{}, err
	}
	defer func() {
		for index := range previousEntries {
			previousEntries[index].Key = ""
		}
	}()
	configuredVersions := map[string]struct{}{activeVersion: {}}
	previousKeys := make([]ashrclone.IdentitySessionHMACKey, 0, len(previousEntries))
	keepPreviousKeys := false
	defer func() {
		if keepPreviousKeys {
			return
		}
		for index := range previousKeys {
			zeroBytes(previousKeys[index].Key)
		}
	}()
	for index, entry := range previousEntries {
		version := strings.TrimSpace(entry.Version)
		if !validIdentitySessionKeyVersion(version) {
			return identitySessionHMACRuntimeConfig{}, fmt.Errorf(
				"ASHR_IDENTITY_SESSION_HMAC_PREVIOUS_KEYS_JSON entry %d has an invalid version",
				index,
			)
		}
		if len(entry.Key) < 32 {
			return identitySessionHMACRuntimeConfig{}, fmt.Errorf(
				"ASHR_IDENTITY_SESSION_HMAC_PREVIOUS_KEYS_JSON entry %d has a key shorter than 32 bytes",
				index,
			)
		}
		if _, duplicate := configuredVersions[version]; duplicate {
			return identitySessionHMACRuntimeConfig{}, fmt.Errorf(
				"ASHR_IDENTITY_SESSION_HMAC_PREVIOUS_KEYS_JSON entry %d duplicates a key version",
				index,
			)
		}
		retireAt, parseErr := time.Parse(time.RFC3339, strings.TrimSpace(entry.RetireAt))
		if parseErr != nil {
			return identitySessionHMACRuntimeConfig{}, fmt.Errorf(
				"ASHR_IDENTITY_SESSION_HMAC_PREVIOUS_KEYS_JSON entry %d has an invalid retire_at",
				index,
			)
		}
		configuredVersions[version] = struct{}{}
		previousKeys = append(previousKeys, ashrclone.IdentitySessionHMACKey{
			Version:  version,
			Key:      []byte(entry.Key),
			RetireAt: retireAt,
		})
	}
	if _, ok := configuredVersions[legacyVersion]; !ok {
		return identitySessionHMACRuntimeConfig{}, fmt.Errorf(
			"ASHR_IDENTITY_SESSION_HMAC_LEGACY_VERSION must reference a configured key version",
		)
	}
	keepPreviousKeys = true
	return identitySessionHMACRuntimeConfig{
		activeVersion: activeVersion,
		activeKey:     []byte(activeKey),
		previousKeys:  previousKeys,
		legacyVersion: legacyVersion,
	}, nil
}

func decodeIdentitySessionPreviousKeys(raw string) ([]identitySessionPreviousKeyEnv, error) {
	if strings.TrimSpace(raw) == "" {
		return []identitySessionPreviousKeyEnv{}, nil
	}
	decoder := json.NewDecoder(strings.NewReader(raw))
	decoder.DisallowUnknownFields()
	var entries []identitySessionPreviousKeyEnv
	if err := decoder.Decode(&entries); err != nil || entries == nil {
		return nil, fmt.Errorf("ASHR_IDENTITY_SESSION_HMAC_PREVIOUS_KEYS_JSON must be a JSON array of version and key objects")
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return nil, fmt.Errorf("ASHR_IDENTITY_SESSION_HMAC_PREVIOUS_KEYS_JSON must contain exactly one JSON array")
	}
	return entries, nil
}

func validIdentitySessionKeyVersion(version string) bool {
	if len(version) < 1 || len(version) > 32 {
		return false
	}
	for _, character := range version {
		if (character < 'a' || character > 'z') &&
			(character < 'A' || character > 'Z') &&
			(character < '0' || character > '9') &&
			character != '_' && character != '-' {
			return false
		}
	}
	return true
}

func (config *identitySessionHMACRuntimeConfig) clear() {
	if config == nil {
		return
	}
	zeroBytes(config.activeKey)
	for index := range config.previousKeys {
		zeroBytes(config.previousKeys[index].Key)
	}
	config.previousKeys = nil
	config.activeVersion = ""
	config.legacyVersion = ""
}

func zeroBytes(value []byte) {
	for index := range value {
		value[index] = 0
	}
}

func productionIdentitySessionReceiptTransportFromEnv(
	lookup func(string) (string, bool),
) (ashrclone.IdentitySessionReceiptTransport, error) {
	intentKey := ""
	if dedicatedKey, present := lookup("ASHR_IDENTITY_BROWSER_INTENT_KEY"); present {
		if dedicatedKey == "" ||
			dedicatedKey != strings.TrimSpace(dedicatedKey) ||
			len(dedicatedKey) < 32 ||
			strings.ContainsAny(dedicatedKey, "\x00\r\n\t") {
			return nil, fmt.Errorf(
				"ASHR_IDENTITY_BROWSER_INTENT_KEY must contain at least 32 normalized bytes",
			)
		}
		intentKey = dedicatedKey
	} else {
		intentKey = envRaw(lookup, "ASHR_IDENTITY_VERIFICATION_HMAC_KEY")
		if intentKey != strings.TrimSpace(intentKey) ||
			len(intentKey) < 32 ||
			strings.ContainsAny(intentKey, "\x00\r\n\t") {
			return nil, fmt.Errorf(
				"ASHR_IDENTITY_BROWSER_INTENT_KEY or ASHR_IDENTITY_VERIFICATION_HMAC_KEY must contain at least 32 normalized bytes",
			)
		}
	}
	maxLifetime := 24 * time.Hour
	refreshMaxLifetime := 30 * 24 * time.Hour
	if raw := env(lookup, "ASHR_IDENTITY_SESSION_COOKIE_MAX_AGE_SECONDS"); raw != "" {
		seconds, err := strconv.Atoi(raw)
		if err != nil || seconds < 1 || seconds > 24*60*60 {
			return nil, fmt.Errorf("ASHR_IDENTITY_SESSION_COOKIE_MAX_AGE_SECONDS must be between 1 and 86400")
		}
		maxLifetime = time.Duration(seconds) * time.Second
	}
	if raw := env(lookup, "ASHR_IDENTITY_REFRESH_COOKIE_MAX_AGE_SECONDS"); raw != "" {
		seconds, err := strconv.Atoi(raw)
		if err != nil || seconds < 1 || seconds > 90*24*60*60 {
			return nil, fmt.Errorf("ASHR_IDENTITY_REFRESH_COOKIE_MAX_AGE_SECONDS must be between 1 and 7776000")
		}
		refreshMaxLifetime = time.Duration(seconds) * time.Second
	}
	trustedProxyCIDRs := make([]netip.Prefix, 0)
	if raw := env(lookup, "ASHR_IDENTITY_SESSION_COOKIE_TRUSTED_PROXY_CIDRS"); raw != "" {
		seen := make(map[netip.Prefix]struct{})
		for _, item := range strings.Split(raw, ",") {
			prefix, err := netip.ParsePrefix(strings.TrimSpace(item))
			if err != nil {
				return nil, fmt.Errorf("ASHR_IDENTITY_SESSION_COOKIE_TRUSTED_PROXY_CIDRS contains an invalid CIDR")
			}
			prefix = prefix.Masked()
			if _, duplicate := seen[prefix]; duplicate {
				return nil, fmt.Errorf("ASHR_IDENTITY_SESSION_COOKIE_TRUSTED_PROXY_CIDRS contains a duplicate CIDR")
			}
			seen[prefix] = struct{}{}
			trustedProxyCIDRs = append(trustedProxyCIDRs, prefix)
		}
	}
	transport, err := ashrclone.NewIdentitySessionCookieTransport(
		ashrclone.IdentitySessionCookieTransportOptions{
			MaxLifetime:        maxLifetime,
			RefreshMaxLifetime: refreshMaxLifetime,
			TrustedProxyCIDRs:  trustedProxyCIDRs,
			IntentKey:          []byte(intentKey),
		},
	)
	if err != nil {
		return nil, fmt.Errorf("configure production identity session cookie transport: %w", err)
	}
	return transport, nil
}

func developmentIdentityVerificationSenderFromEnv(
	lookup func(string) (string, bool),
) (ashrclone.IdentityVerificationSender, error) {
	if !envTrue(lookup, "ASHR_IDENTITY_VERIFICATION_SMTP_ENABLED") {
		return &ashrclone.MemoryIdentityVerificationSender{}, nil
	}
	host := env(lookup, "ASHR_SMTP_HOST")
	portValue := env(lookup, "ASHR_SMTP_PORT")
	from := env(lookup, "ASHR_SMTP_FROM")
	authCode := envRaw(lookup, "ASHR_SMTP_AUTH_CODE")
	browserVerificationURL := env(lookup, "ASHR_IDENTITY_VERIFICATION_BROWSER_URL")
	missing := make([]string, 0, 5)
	if host == "" {
		missing = append(missing, "ASHR_SMTP_HOST")
	}
	if portValue == "" {
		missing = append(missing, "ASHR_SMTP_PORT")
	}
	if from == "" {
		missing = append(missing, "ASHR_SMTP_FROM")
	}
	if strings.TrimSpace(authCode) == "" {
		missing = append(missing, "ASHR_SMTP_AUTH_CODE")
	}
	if browserVerificationURL == "" {
		missing = append(missing, "ASHR_IDENTITY_VERIFICATION_BROWSER_URL")
	}
	if len(missing) != 0 {
		return nil, fmt.Errorf("development identity verification SMTP requires complete configuration: %s", strings.Join(missing, ", "))
	}
	port, err := strconv.Atoi(portValue)
	if err != nil || port < 1 || port > 65535 {
		return nil, fmt.Errorf("development identity verification SMTP requires a valid ASHR_SMTP_PORT")
	}
	sender, err := ashrclone.NewSMTPIdentityVerificationSender(ashrclone.SMTPIdentityVerificationSenderOptions{
		Host: host, Port: port, From: from, AuthCode: authCode,
		BrowserVerificationURL: browserVerificationURL,
	})
	if err != nil {
		return nil, fmt.Errorf("configure development identity verification SMTP sender: invalid SMTP configuration")
	}
	return sender, nil
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
