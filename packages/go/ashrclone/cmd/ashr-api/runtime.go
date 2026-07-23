package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/netip"
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
)

var openIdentityDatabase = sql.Open

type identityRuntime struct {
	mode                       string
	unifiedIdentity            *ashrclone.UnifiedIdentityService
	identityLifecycle          *ashrclone.IdentityLifecycleService
	identitySessions           ashrclone.IdentityHTTPSessionResolver
	postgres                   *ashrclone.ProductionIdentityStore
	outbox                     ashrclone.OAuthRevocationOutboxStore
	verification               *ashrclone.IdentityVerificationService
	verificationResponsePolicy *ashrclone.IdentityVerificationResponsePolicy
	sessionReceiptTransport    ashrclone.IdentitySessionReceiptTransport
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
		store, err := openProductionIdentityStoreFromEnv(dsn, lookup)
		if err != nil {
			return identityRuntime{}, err
		}
		verificationEnabled := envTrue(lookup, "ASHR_IDENTITY_VERIFICATION_ENABLED")
		var deliveryVault *productionIdentityDeliveryVaultRuntime
		closeResources := func() error {
			deliveryVault.close()
			return store.Close()
		}
		if verificationEnabled {
			deliveryVault, err = productionIdentityDeliveryVaultFromEnv(lookup)
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
			GitHubEnabled: false,
			GoogleEnabled: false,
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
		if envTrue(lookup, "ASHR_GITHUB_OAUTH_ENABLED") || envTrue(lookup, "ASHR_GOOGLE_OAUTH_ENABLED") {
			_ = closeResources()
			return identityRuntime{}, fmt.Errorf("production OAuth requires an injected external opaque vault; refusing memory or plaintext token storage")
		}
		runtime := identityRuntime{
			mode:              mode,
			identityLifecycle: lifecycle,
			identitySessions:  store,
			postgres:          store,
			outbox:            outbox,
			close:             closeResources,
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
			sessionReceiptTransport, transportErr := productionIdentitySessionReceiptTransportFromEnv(lookup)
			if transportErr != nil {
				verification.Close()
				verificationStore.Close()
				_ = closeResources()
				return identityRuntime{}, transportErr
			}
			runtime.verification = verification
			runtime.verificationResponsePolicy = responsePolicy
			runtime.sessionReceiptTransport = sessionReceiptTransport
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
	intentKey := envRaw(lookup, "ASHR_IDENTITY_VERIFICATION_HMAC_KEY")
	if len(intentKey) < 32 {
		return nil, fmt.Errorf("ASHR_IDENTITY_VERIFICATION_HMAC_KEY must contain at least 32 bytes")
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
