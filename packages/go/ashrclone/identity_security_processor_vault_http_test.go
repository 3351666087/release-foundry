package ashrclone

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

type identitySecurityVaultRotatingTokenProvider struct {
	mu    sync.Mutex
	token string
	err   error
	reads int
}

func (provider *identitySecurityVaultRotatingTokenProvider) ReadIdentitySecurityVaultToken(
	context.Context,
) ([]byte, error) {
	provider.mu.Lock()
	defer provider.mu.Unlock()
	provider.reads++
	if provider.err != nil {
		return nil, provider.err
	}
	return []byte(provider.token), nil
}

func (provider *identitySecurityVaultRotatingTokenProvider) setToken(token string) {
	provider.mu.Lock()
	defer provider.mu.Unlock()
	provider.token = token
}

func TestHashiCorpVaultKVV2IdentitySecurityProcessorVaultRoundTripAndKeyRotation(
	t *testing.T,
) {
	type stored struct {
		payload string
		version uint64
	}
	records := make(map[string]stored)
	var mu sync.Mutex
	tokenProvider := &identitySecurityVaultRotatingTokenProvider{
		token: "a1_test_fixture_vault_token_primary_0001",
	}
	keyV1 := base64.StdEncoding.EncodeToString(bytes.Repeat([]byte{0x11}, 32))
	keyV2 := base64.StdEncoding.EncodeToString(bytes.Repeat([]byte{0x22}, 32))
	server := httptest.NewTLSServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		if !strings.HasPrefix(
			request.Header.Get("X-Vault-Token"),
			"a1_test_fixture_vault_token_",
		) {
			t.Error("Vault request omitted the projected token")
		}
		if request.Header.Get("X-Vault-Namespace") != "admin/ashr" {
			t.Error("Vault namespace was not preserved")
		}
		if request.URL.Path == "/v1/secret/data/ashr/identity-security/keyring" {
			writeIdentitySecurityVaultTestJSON(writer, http.StatusOK, map[string]any{
				"data": map[string]any{
					"data": map[string]any{
						"schema_version": "ashr.identity_security_processor_keyring.v1",
						"active_version": "key-v2",
						"keys": map[string]string{
							"key-v1": keyV1,
							"key-v2": keyV2,
						},
					},
					"metadata": identitySecurityVaultTestMetadata(3),
				},
			})
			return
		}
		const dataPrefix = "/v1/secret/data/ashr/identity-security/records/"
		const metadataPrefix = "/v1/secret/metadata/ashr/identity-security/records/"
		switch {
		case strings.HasPrefix(request.URL.Path, dataPrefix):
			refToken := strings.TrimPrefix(request.URL.Path, dataPrefix)
			mu.Lock()
			defer mu.Unlock()
			switch request.Method {
			case http.MethodGet:
				record, ok := records[refToken]
				if !ok {
					writeIdentitySecurityVaultTestJSON(
						writer,
						http.StatusNotFound,
						map[string]any{"errors": []string{"missing"}},
					)
					return
				}
				writeIdentitySecurityVaultTestJSON(writer, http.StatusOK, map[string]any{
					"data": map[string]any{
						"data": map[string]string{
							"payload_base64": record.payload,
						},
						"metadata": identitySecurityVaultTestMetadata(record.version),
					},
				})
			case http.MethodPost:
				var payload struct {
					Options struct {
						CAS uint64 `json:"cas"`
					} `json:"options"`
					Data struct {
						PayloadBase64 string `json:"payload_base64"`
					} `json:"data"`
				}
				decoder := json.NewDecoder(request.Body)
				decoder.DisallowUnknownFields()
				if err := decoder.Decode(&payload); err != nil {
					t.Errorf("decode Vault write: %v", err)
					writer.WriteHeader(http.StatusBadRequest)
					return
				}
				current, exists := records[refToken]
				conflict := payload.Options.CAS == 0 && exists ||
					payload.Options.CAS > 0 &&
						(!exists || current.version != payload.Options.CAS)
				if conflict {
					writeIdentitySecurityVaultTestJSON(
						writer,
						http.StatusBadRequest,
						map[string]any{"errors": []string{"cas mismatch"}},
					)
					return
				}
				version := uint64(1)
				if exists {
					version = current.version + 1
				}
				records[refToken] = stored{
					payload: payload.Data.PayloadBase64,
					version: version,
				}
				writeIdentitySecurityVaultTestJSON(writer, http.StatusOK, map[string]any{
					"data": identitySecurityVaultTestMetadata(version),
				})
			default:
				writer.WriteHeader(http.StatusMethodNotAllowed)
			}
		case strings.HasPrefix(request.URL.Path, metadataPrefix):
			if request.Method != http.MethodDelete {
				writer.WriteHeader(http.StatusMethodNotAllowed)
				return
			}
			refToken := strings.TrimPrefix(request.URL.Path, metadataPrefix)
			mu.Lock()
			delete(records, refToken)
			mu.Unlock()
			writer.WriteHeader(http.StatusNoContent)
		default:
			writer.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	vault, err := NewHashiCorpVaultKVV2IdentitySecurityProcessorVault(
		HashiCorpVaultKVV2IdentitySecurityProcessorVaultOptions{
			DataEndpointPrefix: server.URL +
				"/v1/secret/data/ashr/identity-security/records",
			MetadataEndpointPrefix: server.URL +
				"/v1/secret/metadata/ashr/identity-security/records",
			Namespace:     "admin/ashr",
			Client:        server.Client(),
			TokenProvider: tokenProvider,
			Timeout:       time.Second,
		},
	)
	if err != nil {
		t.Fatalf("new Vault adapter: %v", err)
	}
	resolver, err := NewHashiCorpVaultKVV2IdentitySecurityProcessorKeyResolver(
		HashiCorpVaultKVV2IdentitySecurityProcessorKeyResolverOptions{
			Endpoint: server.URL +
				"/v1/secret/data/ashr/identity-security/keyring",
			Namespace:     "admin/ashr",
			Client:        server.Client(),
			TokenProvider: tokenProvider,
			Timeout:       time.Second,
		},
	)
	if err != nil {
		t.Fatalf("new key resolver: %v", err)
	}
	if err := vault.Ready(context.Background()); err != nil {
		t.Fatalf("Vault readiness: %v", err)
	}
	refToken := base64.RawURLEncoding.EncodeToString(bytes.Repeat([]byte{0x33}, 32))
	payloadV1 := []byte(`{"schema_version":"record.v1","secret":"not-logged"}`)
	created, err := vault.Create(context.Background(), refToken, payloadV1)
	if err != nil || !created {
		t.Fatalf("create Vault record: created=%v err=%v", created, err)
	}
	created, err = vault.Create(context.Background(), refToken, payloadV1)
	if err != nil || created {
		t.Fatalf("CAS 0 retry did not report existing record: created=%v err=%v", created, err)
	}
	loaded, version, err := vault.Read(context.Background(), refToken)
	if err != nil || version != 1 || !bytes.Equal(loaded, payloadV1) {
		t.Fatalf("read Vault record: version=%d len=%d err=%v", version, len(loaded), err)
	}
	clear(loaded)
	tokenProvider.setToken("a1_test_fixture_vault_token_rotated_0002")
	payloadV2 := []byte(`{"schema_version":"record.v2","secret":"still-not-logged"}`)
	swapped, err := vault.CompareAndSwap(
		context.Background(),
		refToken,
		version,
		payloadV2,
	)
	if err != nil || !swapped {
		t.Fatalf("CAS Vault record: swapped=%v err=%v", swapped, err)
	}
	swapped, err = vault.CompareAndSwap(
		context.Background(),
		refToken,
		version,
		payloadV2,
	)
	if err != nil || swapped {
		t.Fatalf("stale CAS did not fail safely: swapped=%v err=%v", swapped, err)
	}
	ring, err := resolver.ResolveIdentitySecurityProcessorKeys(context.Background())
	if err != nil || ring.ActiveVersion != "key-v2" ||
		len(ring.Keys) != 2 ||
		!bytes.Equal(ring.Keys["key-v1"], bytes.Repeat([]byte{0x11}, 32)) ||
		!bytes.Equal(ring.Keys["key-v2"], bytes.Repeat([]byte{0x22}, 32)) {
		t.Fatalf("resolve active/previous key ring: versions=%d err=%v", len(ring.Keys), err)
	}
	clearIdentitySecurityProcessorKeyRing(&ring)
	if err := vault.Delete(context.Background(), refToken); err != nil {
		t.Fatalf("delete Vault metadata: %v", err)
	}
	if _, _, err := vault.Read(
		context.Background(),
		refToken,
	); !errors.Is(err, ErrIdentitySecurityProcessorVaultRecordNotFound) {
		t.Fatalf("deleted Vault record remained readable: %v", err)
	}
}

func TestHashiCorpVaultKVV2IdentitySecurityProcessorVaultRejectsRedirectAndRedacts(
	t *testing.T,
) {
	const secretMarker = "processor-secret-must-not-leak"
	var redirected atomic.Int32
	server := httptest.NewTLSServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		switch {
		case strings.Contains(request.URL.Path, "/data/"):
			http.Redirect(writer, request, "/capture", http.StatusTemporaryRedirect)
		case request.URL.Path == "/capture":
			redirected.Add(1)
			writer.WriteHeader(http.StatusNoContent)
		default:
			writer.WriteHeader(http.StatusInternalServerError)
			_, _ = writer.Write([]byte(secretMarker))
		}
	}))
	defer server.Close()
	vault := newIdentitySecurityVaultHTTPTestAdapter(t, server, server.Client())
	refToken := base64.RawURLEncoding.EncodeToString(bytes.Repeat([]byte{0x44}, 32))
	_, err := vault.Create(context.Background(), refToken, []byte(secretMarker))
	if !errors.Is(err, ErrIdentitySecurityProcessorUnavailable) ||
		strings.Contains(err.Error(), secretMarker) {
		t.Fatalf("redirect failure was not safely rejected: %v", err)
	}
	if redirected.Load() != 0 {
		t.Fatalf("secret-bearing Vault request followed a redirect")
	}
}

func TestHashiCorpVaultKVV2IdentitySecurityProcessorVaultRejectsUnknownResponse(
	t *testing.T,
) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		writeIdentitySecurityVaultTestJSON(writer, http.StatusOK, map[string]any{
			"data": map[string]any{
				"data": map[string]string{
					"payload_base64": base64.StdEncoding.EncodeToString(
						[]byte("payload"),
					),
				},
				"metadata": identitySecurityVaultTestMetadata(1),
			},
			"unexpected": "fail-closed",
		})
	}))
	defer server.Close()
	vault := newIdentitySecurityVaultHTTPTestAdapter(t, server, server.Client())
	refToken := base64.RawURLEncoding.EncodeToString(bytes.Repeat([]byte{0x55}, 32))
	if _, _, err := vault.Read(
		context.Background(),
		refToken,
	); !errors.Is(err, ErrIdentitySecurityProcessorUnavailable) {
		t.Fatalf("unknown Vault response field was accepted: %v", err)
	}
}

func TestHashiCorpVaultKVV2IdentitySecurityProcessorVaultConfigurationAndTokenFile(
	t *testing.T,
) {
	tokenPath := filepath.Join(t.TempDir(), "vault-token")
	if err := os.WriteFile(
		tokenPath,
		[]byte("a1_test_fixture_vault_token_primary_0001\n"),
		0o600,
	); err != nil {
		t.Fatalf("write projected token: %v", err)
	}
	provider := FileIdentitySecurityVaultTokenProvider{Path: tokenPath}
	first, err := provider.ReadIdentitySecurityVaultToken(context.Background())
	if err != nil || string(first) != "a1_test_fixture_vault_token_primary_0001" {
		t.Fatalf("read projected token: len=%d err=%v", len(first), err)
	}
	clear(first)
	if err := os.WriteFile(
		tokenPath,
		[]byte("a1_test_fixture_vault_token_rotated_0002\n"),
		0o600,
	); err != nil {
		t.Fatalf("rotate projected token: %v", err)
	}
	second, err := provider.ReadIdentitySecurityVaultToken(context.Background())
	if err != nil || string(second) != "a1_test_fixture_vault_token_rotated_0002" {
		t.Fatalf("read rotated projected token: len=%d err=%v", len(second), err)
	}
	clear(second)
	if err := os.WriteFile(tokenPath, []byte("short"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := provider.ReadIdentitySecurityVaultToken(
		context.Background(),
	); !errors.Is(err, ErrIdentitySecurityProcessorUnavailable) {
		t.Fatalf("unsafe projected token was accepted: %v", err)
	}

	valid := HashiCorpVaultKVV2IdentitySecurityProcessorVaultOptions{
		DataEndpointPrefix:     "https://vault.example.test/v1/secret/data/ashr/identity-security/records",
		MetadataEndpointPrefix: "https://vault.example.test/v1/secret/metadata/ashr/identity-security/records",
		Namespace:              "admin/ashr",
		Client:                 &http.Client{},
		TokenProvider:          &identitySecurityVaultRotatingTokenProvider{token: "a1_test_fixture_vault_token_primary_0001"},
		Timeout:                time.Second,
	}
	for name, mutate := range map[string]func(
		*HashiCorpVaultKVV2IdentitySecurityProcessorVaultOptions,
	){
		"missing client": func(options *HashiCorpVaultKVV2IdentitySecurityProcessorVaultOptions) {
			options.Client = nil
		},
		"raw HTTP": func(options *HashiCorpVaultKVV2IdentitySecurityProcessorVaultOptions) {
			options.DataEndpointPrefix = strings.Replace(
				options.DataEndpointPrefix,
				"https://",
				"http://",
				1,
			)
		},
		"query": func(options *HashiCorpVaultKVV2IdentitySecurityProcessorVaultOptions) {
			options.MetadataEndpointPrefix += "?unsafe=true"
		},
		"mismatched path": func(options *HashiCorpVaultKVV2IdentitySecurityProcessorVaultOptions) {
			options.MetadataEndpointPrefix = strings.Replace(
				options.MetadataEndpointPrefix,
				"/records",
				"/other",
				1,
			)
		},
		"invalid namespace": func(options *HashiCorpVaultKVV2IdentitySecurityProcessorVaultOptions) {
			options.Namespace = "unsafe namespace"
		},
		"missing timeout": func(options *HashiCorpVaultKVV2IdentitySecurityProcessorVaultOptions) {
			options.Timeout = 0
		},
	} {
		t.Run(name, func(t *testing.T) {
			options := valid
			mutate(&options)
			if _, err := NewHashiCorpVaultKVV2IdentitySecurityProcessorVault(
				options,
			); err == nil {
				t.Fatalf("invalid Vault configuration was accepted")
			}
		})
	}
}

func newIdentitySecurityVaultHTTPTestAdapter(
	t *testing.T,
	server *httptest.Server,
	client *http.Client,
) *HashiCorpVaultKVV2IdentitySecurityProcessorVault {
	t.Helper()
	vault, err := NewHashiCorpVaultKVV2IdentitySecurityProcessorVault(
		HashiCorpVaultKVV2IdentitySecurityProcessorVaultOptions{
			DataEndpointPrefix: server.URL +
				"/v1/secret/data/ashr/identity-security/records",
			MetadataEndpointPrefix: server.URL +
				"/v1/secret/metadata/ashr/identity-security/records",
			Client: client,
			TokenProvider: &identitySecurityVaultRotatingTokenProvider{
				token: "a1_test_fixture_vault_token_primary_0001",
			},
			Timeout: time.Second,
		},
	)
	if err != nil {
		t.Fatalf("new Vault HTTP test adapter: %v", err)
	}
	return vault
}

func identitySecurityVaultTestMetadata(version uint64) map[string]any {
	return map[string]any{
		"created_time":    "2026-07-25T09:30:00Z",
		"custom_metadata": nil,
		"deletion_time":   "",
		"destroyed":       false,
		"version":         version,
	}
}

func writeIdentitySecurityVaultTestJSON(
	writer http.ResponseWriter,
	status int,
	payload any,
) {
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(status)
	if err := json.NewEncoder(writer).Encode(payload); err != nil {
		panic(fmt.Sprintf("encode Vault test response: %v", err))
	}
}

var _ IdentitySecurityVaultTokenProvider = (*identitySecurityVaultRotatingTokenProvider)(
	nil,
)
