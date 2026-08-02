package releasefoundry

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strings"
	"time"
)

const (
	maxIdentitySecurityVaultTokenBytes    = 8 * 1024
	maxIdentitySecurityVaultRequestBytes  = 384 * 1024
	maxIdentitySecurityVaultResponseBytes = 512 * 1024
	maxIdentitySecurityKeyRingBytes       = 64 * 1024
)

var identitySecurityVaultNamespacePattern = regexp.MustCompile(
	`^[A-Za-z0-9][A-Za-z0-9_-]{0,62}(?:/[A-Za-z0-9][A-Za-z0-9_-]{0,62}){0,7}/?$`,
)
var identitySecurityVaultTokenPattern = regexp.MustCompile(
	`^[A-Za-z0-9][A-Za-z0-9._-]+$`,
)
var identitySecurityVaultRecordTokenPattern = regexp.MustCompile(
	`^[A-Za-z0-9_-]{43}$`,
)

type IdentitySecurityVaultTokenProvider interface {
	ReadIdentitySecurityVaultToken(context.Context) ([]byte, error)
}

type FileIdentitySecurityVaultTokenProvider struct {
	Path string
}

func (provider FileIdentitySecurityVaultTokenProvider) ReadIdentitySecurityVaultToken(
	ctx context.Context,
) ([]byte, error) {
	if ctx == nil || ctx.Err() != nil {
		return nil, ErrIdentitySecurityProcessorUnavailable
	}
	path := strings.TrimSpace(provider.Path)
	if path == "" || path != provider.Path ||
		strings.ContainsAny(path, "\x00\r\n") {
		return nil, ErrIdentitySecurityProcessorUnavailable
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, ErrIdentitySecurityProcessorUnavailable
	}
	defer file.Close()
	rawToken, err := io.ReadAll(
		io.LimitReader(file, maxIdentitySecurityVaultTokenBytes+1),
	)
	if err != nil || len(rawToken) > maxIdentitySecurityVaultTokenBytes {
		clear(rawToken)
		return nil, ErrIdentitySecurityProcessorUnavailable
	}
	token := append([]byte(nil), bytes.TrimSpace(rawToken)...)
	clear(rawToken)
	if !validIdentitySecurityVaultToken(token) {
		clear(token)
		return nil, ErrIdentitySecurityProcessorUnavailable
	}
	return token, nil
}

type HashiCorpVaultKVV2IdentitySecurityProcessorVaultOptions struct {
	DataEndpointPrefix     string
	MetadataEndpointPrefix string
	Namespace              string
	Client                 *http.Client
	TokenProvider          IdentitySecurityVaultTokenProvider
	Timeout                time.Duration
}

type HashiCorpVaultKVV2IdentitySecurityProcessorVault struct {
	dataEndpointPrefix     string
	metadataEndpointPrefix string
	client                 *http.Client
	tokenProvider          IdentitySecurityVaultTokenProvider
	namespace              string
	timeout                time.Duration
}

func NewHashiCorpVaultKVV2IdentitySecurityProcessorVault(
	options HashiCorpVaultKVV2IdentitySecurityProcessorVaultOptions,
) (*HashiCorpVaultKVV2IdentitySecurityProcessorVault, error) {
	if options.Client == nil || options.TokenProvider == nil {
		return nil, errors.New("identity security Vault authenticated client and token provider are required")
	}
	dataPrefix, dataURL, err := strictIdentitySecurityVaultKVV2EndpointPrefix(
		options.DataEndpointPrefix,
		"/data/",
	)
	if err != nil {
		return nil, err
	}
	metadataPrefix, metadataURL, err :=
		strictIdentitySecurityVaultKVV2EndpointPrefix(
			options.MetadataEndpointPrefix,
			"/metadata/",
		)
	if err != nil {
		return nil, err
	}
	if dataURL.Scheme != metadataURL.Scheme || dataURL.Host != metadataURL.Host ||
		strings.Replace(dataURL.Path, "/data/", "/metadata/", 1) != metadataURL.Path {
		return nil, errors.New("identity security Vault data and metadata endpoints must identify the same KV v2 path")
	}
	namespace, err := strictIdentitySecurityVaultNamespace(options.Namespace)
	if err != nil {
		return nil, err
	}
	if options.Timeout < time.Millisecond || options.Timeout > 30*time.Second {
		return nil, errors.New("identity security Vault timeout must be between 1ms and 30s")
	}
	client := *options.Client
	client.CheckRedirect = func(*http.Request, []*http.Request) error {
		return errors.New("identity security Vault redirect refused")
	}
	return &HashiCorpVaultKVV2IdentitySecurityProcessorVault{
		dataEndpointPrefix:     dataPrefix,
		metadataEndpointPrefix: metadataPrefix,
		client:                 &client,
		tokenProvider:          options.TokenProvider,
		namespace:              namespace,
		timeout:                options.Timeout,
	}, nil
}

func (vault *HashiCorpVaultKVV2IdentitySecurityProcessorVault) Ready(
	ctx context.Context,
) error {
	if vault == nil || vault.client == nil || vault.tokenProvider == nil ||
		ctx == nil {
		return ErrIdentitySecurityProcessorUnavailable
	}
	_, _, err := vault.Read(ctx, strings.Repeat("A", 43))
	if errors.Is(err, ErrIdentitySecurityProcessorVaultRecordNotFound) {
		return nil
	}
	if err != nil {
		return ErrIdentitySecurityProcessorUnavailable
	}
	return nil
}

func (vault *HashiCorpVaultKVV2IdentitySecurityProcessorVault) Read(
	ctx context.Context,
	refToken string,
) ([]byte, uint64, error) {
	if vault == nil || vault.client == nil || vault.tokenProvider == nil ||
		ctx == nil || !validIdentitySecurityVaultRecordToken(refToken) {
		return nil, 0, ErrIdentitySecurityProcessorUnavailable
	}
	response, err := vault.do(
		ctx,
		http.MethodGet,
		vault.dataEndpointPrefix+"/"+refToken,
		nil,
	)
	if err != nil {
		return nil, 0, err
	}
	defer response.Body.Close()
	if response.StatusCode == http.StatusNotFound {
		drainIdentitySecurityVaultResponse(response.Body)
		return nil, 0, ErrIdentitySecurityProcessorVaultRecordNotFound
	}
	if response.StatusCode != http.StatusOK {
		drainIdentitySecurityVaultResponse(response.Body)
		return nil, 0, ErrIdentitySecurityProcessorUnavailable
	}
	var envelope identitySecurityVaultKVV2ReadEnvelope
	if err := decodeIdentitySecurityVaultJSONResponse(response, &envelope); err != nil ||
		envelope.Data.Metadata.Version == 0 ||
		envelope.Data.Metadata.Destroyed ||
		envelope.Data.Metadata.DeletionTime != "" ||
		envelope.Data.Data.PayloadBase64 == "" {
		return nil, 0, ErrIdentitySecurityProcessorUnavailable
	}
	payload, err := base64.StdEncoding.Strict().DecodeString(
		envelope.Data.Data.PayloadBase64,
	)
	if err != nil || len(payload) == 0 || len(payload) > 256*1024 ||
		base64.StdEncoding.EncodeToString(payload) !=
			envelope.Data.Data.PayloadBase64 {
		clear(payload)
		return nil, 0, ErrIdentitySecurityProcessorUnavailable
	}
	return payload, envelope.Data.Metadata.Version, nil
}

func (vault *HashiCorpVaultKVV2IdentitySecurityProcessorVault) Create(
	ctx context.Context,
	refToken string,
	payload []byte,
) (bool, error) {
	return vault.write(ctx, refToken, 0, payload)
}

func (vault *HashiCorpVaultKVV2IdentitySecurityProcessorVault) CompareAndSwap(
	ctx context.Context,
	refToken string,
	version uint64,
	payload []byte,
) (bool, error) {
	if version == 0 {
		return false, ErrIdentitySecurityProcessorUnavailable
	}
	return vault.write(ctx, refToken, version, payload)
}

func (vault *HashiCorpVaultKVV2IdentitySecurityProcessorVault) Delete(
	ctx context.Context,
	refToken string,
) error {
	if vault == nil || vault.client == nil || vault.tokenProvider == nil ||
		ctx == nil || !validIdentitySecurityVaultRecordToken(refToken) {
		return ErrIdentitySecurityProcessorUnavailable
	}
	response, err := vault.do(
		context.WithoutCancel(ctx),
		http.MethodDelete,
		vault.metadataEndpointPrefix+"/"+refToken,
		nil,
	)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	drainIdentitySecurityVaultResponse(response.Body)
	switch response.StatusCode {
	case http.StatusOK, http.StatusNoContent, http.StatusNotFound:
		return nil
	default:
		return ErrIdentitySecurityProcessorUnavailable
	}
}

func (vault *HashiCorpVaultKVV2IdentitySecurityProcessorVault) write(
	ctx context.Context,
	refToken string,
	version uint64,
	payload []byte,
) (bool, error) {
	if vault == nil || vault.client == nil || vault.tokenProvider == nil ||
		ctx == nil || !validIdentitySecurityVaultRecordToken(refToken) ||
		len(payload) == 0 || len(payload) > 256*1024 {
		return false, ErrIdentitySecurityProcessorUnavailable
	}
	var requestEnvelope struct {
		Options struct {
			CAS uint64 `json:"cas"`
		} `json:"options"`
		Data struct {
			PayloadBase64 string `json:"payload_base64"`
		} `json:"data"`
	}
	requestEnvelope.Options.CAS = version
	requestEnvelope.Data.PayloadBase64 = base64.StdEncoding.EncodeToString(payload)
	requestBody, err := json.Marshal(requestEnvelope)
	requestEnvelope.Data.PayloadBase64 = ""
	if err != nil || len(requestBody) > maxIdentitySecurityVaultRequestBytes {
		clear(requestBody)
		return false, ErrIdentitySecurityProcessorUnavailable
	}
	response, err := vault.do(
		ctx,
		http.MethodPost,
		vault.dataEndpointPrefix+"/"+refToken,
		requestBody,
	)
	clear(requestBody)
	if err != nil {
		return false, err
	}
	defer response.Body.Close()
	if response.StatusCode == http.StatusBadRequest {
		drainIdentitySecurityVaultResponse(response.Body)
		_, currentVersion, readErr := vault.Read(ctx, refToken)
		if readErr != nil {
			return false, ErrIdentitySecurityProcessorUnavailable
		}
		if version == 0 || currentVersion != version {
			return false, nil
		}
		return false, ErrIdentitySecurityProcessorUnavailable
	}
	if response.StatusCode != http.StatusOK {
		drainIdentitySecurityVaultResponse(response.Body)
		return false, ErrIdentitySecurityProcessorUnavailable
	}
	var envelope identitySecurityVaultKVV2WriteEnvelope
	if err := decodeIdentitySecurityVaultJSONResponse(response, &envelope); err != nil ||
		envelope.Data.Version == 0 {
		return false, ErrIdentitySecurityProcessorUnavailable
	}
	if version == 0 && envelope.Data.Version != 1 ||
		version > 0 && envelope.Data.Version != version+1 {
		return false, ErrIdentitySecurityProcessorUnavailable
	}
	return true, nil
}

func (vault *HashiCorpVaultKVV2IdentitySecurityProcessorVault) do(
	ctx context.Context,
	method string,
	endpoint string,
	body []byte,
) (*http.Response, error) {
	callCtx, cancel := context.WithTimeout(ctx, vault.timeout)
	var reader io.Reader
	if len(body) > 0 {
		reader = bytes.NewReader(body)
	}
	request, err := http.NewRequestWithContext(callCtx, method, endpoint, reader)
	if err != nil {
		cancel()
		return nil, ErrIdentitySecurityProcessorUnavailable
	}
	request.Header.Set("Accept", "application/json")
	if len(body) > 0 {
		request.Header.Set("Content-Type", "application/json")
	}
	if vault.namespace != "" {
		request.Header.Set("X-Vault-Namespace", vault.namespace)
	}
	token, err := vault.tokenProvider.ReadIdentitySecurityVaultToken(callCtx)
	if err != nil || !validIdentitySecurityVaultToken(token) {
		clear(token)
		cancel()
		return nil, ErrIdentitySecurityProcessorUnavailable
	}
	request.Header.Set("X-Vault-Token", string(token))
	clear(token)
	response, err := vault.client.Do(request)
	request.Header.Del("X-Vault-Token")
	if err != nil {
		cancel()
		return nil, safeIdentitySecurityVaultHTTPError(err)
	}
	response.Body = &identitySecurityVaultCancelOnCloseBody{
		ReadCloser: response.Body,
		cancel:     cancel,
	}
	return response, nil
}

type HashiCorpVaultKVV2IdentitySecurityProcessorKeyResolverOptions struct {
	Endpoint      string
	Namespace     string
	Client        *http.Client
	TokenProvider IdentitySecurityVaultTokenProvider
	Timeout       time.Duration
}

type HashiCorpVaultKVV2IdentitySecurityProcessorKeyResolver struct {
	endpoint      string
	client        *http.Client
	tokenProvider IdentitySecurityVaultTokenProvider
	namespace     string
	timeout       time.Duration
}

func NewHashiCorpVaultKVV2IdentitySecurityProcessorKeyResolver(
	options HashiCorpVaultKVV2IdentitySecurityProcessorKeyResolverOptions,
) (*HashiCorpVaultKVV2IdentitySecurityProcessorKeyResolver, error) {
	if options.Client == nil || options.TokenProvider == nil {
		return nil, errors.New("identity security key resolver authenticated client and token provider are required")
	}
	endpoint, _, err := strictIdentitySecurityVaultKVV2DataEndpoint(
		options.Endpoint,
	)
	if err != nil {
		return nil, err
	}
	namespace, err := strictIdentitySecurityVaultNamespace(options.Namespace)
	if err != nil {
		return nil, err
	}
	if options.Timeout < time.Millisecond || options.Timeout > 30*time.Second {
		return nil, errors.New("identity security key resolver timeout must be between 1ms and 30s")
	}
	client := *options.Client
	client.CheckRedirect = func(*http.Request, []*http.Request) error {
		return errors.New("identity security key resolver redirect refused")
	}
	return &HashiCorpVaultKVV2IdentitySecurityProcessorKeyResolver{
		endpoint:      endpoint,
		client:        &client,
		tokenProvider: options.TokenProvider,
		namespace:     namespace,
		timeout:       options.Timeout,
	}, nil
}

func (resolver *HashiCorpVaultKVV2IdentitySecurityProcessorKeyResolver) ResolveIdentitySecurityProcessorKeys(
	ctx context.Context,
) (IdentitySecurityProcessorKeyRing, error) {
	if resolver == nil || resolver.client == nil || resolver.tokenProvider == nil ||
		ctx == nil {
		return IdentitySecurityProcessorKeyRing{}, ErrIdentitySecurityProcessorUnavailable
	}
	callCtx, cancel := context.WithTimeout(ctx, resolver.timeout)
	defer cancel()
	request, err := http.NewRequestWithContext(
		callCtx,
		http.MethodGet,
		resolver.endpoint,
		nil,
	)
	if err != nil {
		return IdentitySecurityProcessorKeyRing{}, ErrIdentitySecurityProcessorUnavailable
	}
	request.Header.Set("Accept", "application/json")
	if resolver.namespace != "" {
		request.Header.Set("X-Vault-Namespace", resolver.namespace)
	}
	token, err := resolver.tokenProvider.ReadIdentitySecurityVaultToken(callCtx)
	if err != nil || !validIdentitySecurityVaultToken(token) {
		clear(token)
		return IdentitySecurityProcessorKeyRing{}, ErrIdentitySecurityProcessorUnavailable
	}
	request.Header.Set("X-Vault-Token", string(token))
	clear(token)
	response, err := resolver.client.Do(request)
	request.Header.Del("X-Vault-Token")
	if err != nil {
		return IdentitySecurityProcessorKeyRing{}, safeIdentitySecurityVaultHTTPError(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		drainIdentitySecurityVaultResponse(response.Body)
		return IdentitySecurityProcessorKeyRing{}, ErrIdentitySecurityProcessorUnavailable
	}
	var envelope identitySecurityVaultKVV2KeyRingEnvelope
	if err := decodeIdentitySecurityVaultJSONResponse(response, &envelope); err != nil ||
		envelope.Data.Metadata.Version == 0 ||
		envelope.Data.Metadata.Destroyed ||
		envelope.Data.Metadata.DeletionTime != "" ||
		envelope.Data.Data.SchemaVersion !=
			"releasefoundry.identity_security_processor_keyring.v1" ||
		!identitySecurityProcessorKeyVersionPattern.MatchString(
			envelope.Data.Data.ActiveVersion,
		) ||
		len(envelope.Data.Data.Keys) < 1 ||
		len(envelope.Data.Data.Keys) > 8 {
		return IdentitySecurityProcessorKeyRing{}, ErrIdentitySecurityProcessorUnavailable
	}
	ring := IdentitySecurityProcessorKeyRing{
		ActiveVersion: envelope.Data.Data.ActiveVersion,
		Keys:          make(map[string][]byte, len(envelope.Data.Data.Keys)),
	}
	for version, encodedKey := range envelope.Data.Data.Keys {
		if !identitySecurityProcessorKeyVersionPattern.MatchString(version) ||
			encodedKey == "" {
			clearIdentitySecurityProcessorKeyRing(&ring)
			return IdentitySecurityProcessorKeyRing{}, ErrIdentitySecurityProcessorUnavailable
		}
		key, err := base64.StdEncoding.Strict().DecodeString(encodedKey)
		if err != nil || len(key) < 32 || len(key) > 64 ||
			base64.StdEncoding.EncodeToString(key) != encodedKey {
			clear(key)
			clearIdentitySecurityProcessorKeyRing(&ring)
			return IdentitySecurityProcessorKeyRing{}, ErrIdentitySecurityProcessorUnavailable
		}
		ring.Keys[version] = key
	}
	if len(ring.Keys[ring.ActiveVersion]) == 0 {
		clearIdentitySecurityProcessorKeyRing(&ring)
		return IdentitySecurityProcessorKeyRing{}, ErrIdentitySecurityProcessorUnavailable
	}
	return ring, nil
}

type identitySecurityVaultKVV2ResponseBase struct {
	RequestID     string          `json:"request_id"`
	LeaseID       string          `json:"lease_id"`
	Renewable     bool            `json:"renewable"`
	LeaseDuration int64           `json:"lease_duration"`
	WrapInfo      json.RawMessage `json:"wrap_info"`
	Warnings      json.RawMessage `json:"warnings"`
	Auth          json.RawMessage `json:"auth"`
	MountType     string          `json:"mount_type"`
}

type identitySecurityVaultKVV2Metadata struct {
	CreatedTime    string            `json:"created_time"`
	CustomMetadata map[string]string `json:"custom_metadata"`
	DeletionTime   string            `json:"deletion_time"`
	Destroyed      bool              `json:"destroyed"`
	Version        uint64            `json:"version"`
}

type identitySecurityVaultKVV2ReadEnvelope struct {
	identitySecurityVaultKVV2ResponseBase
	Data struct {
		Data struct {
			PayloadBase64 string `json:"payload_base64"`
		} `json:"data"`
		Metadata identitySecurityVaultKVV2Metadata `json:"metadata"`
	} `json:"data"`
}

type identitySecurityVaultKVV2WriteEnvelope struct {
	identitySecurityVaultKVV2ResponseBase
	Data identitySecurityVaultKVV2Metadata `json:"data"`
}

type identitySecurityVaultKVV2KeyRingEnvelope struct {
	identitySecurityVaultKVV2ResponseBase
	Data struct {
		Data struct {
			SchemaVersion string            `json:"schema_version"`
			ActiveVersion string            `json:"active_version"`
			Keys          map[string]string `json:"keys"`
		} `json:"data"`
		Metadata identitySecurityVaultKVV2Metadata `json:"metadata"`
	} `json:"data"`
}

func strictIdentitySecurityVaultKVV2EndpointPrefix(
	raw string,
	requiredSegment string,
) (string, *url.URL, error) {
	validated, parsed, err := strictIdentitySecurityVaultHTTPSURL(raw)
	if err != nil || !strings.Contains(parsedPath(parsed), requiredSegment) ||
		strings.HasSuffix(parsedPath(parsed), requiredSegment) {
		return "", nil, errors.New("identity security Vault endpoint must be an exact HTTPS KV v2 path")
	}
	validated = strings.TrimSuffix(validated, "/")
	parsed.Path = strings.TrimSuffix(parsed.Path, "/")
	return validated, parsed, nil
}

func strictIdentitySecurityVaultKVV2DataEndpoint(
	raw string,
) (string, *url.URL, error) {
	validated, parsed, err := strictIdentitySecurityVaultHTTPSURL(raw)
	if err != nil || !strings.Contains(parsedPath(parsed), "/data/") ||
		strings.HasSuffix(parsedPath(parsed), "/data/") {
		return "", nil, errors.New("identity security key resolver endpoint must be an exact HTTPS KV v2 data path")
	}
	return validated, parsed, nil
}

func strictIdentitySecurityVaultHTTPSURL(
	raw string,
) (string, *url.URL, error) {
	if raw == "" || raw != strings.TrimSpace(raw) ||
		strings.ContainsAny(raw, "\x00\r\n\t") {
		return "", nil, errors.New("identity security Vault endpoint must be an absolute HTTPS URL")
	}
	parsed, err := url.ParseRequestURI(raw)
	if err != nil || parsed.Scheme != "https" || parsed.Host == "" ||
		parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" ||
		!strings.HasPrefix(parsed.Path, "/v1/") ||
		strings.Contains(parsed.Path, "//") ||
		strings.HasSuffix(parsed.Path, ".") {
		return "", nil, errors.New("identity security Vault endpoint must be an absolute HTTPS v1 URL without query or fragment")
	}
	return parsed.String(), parsed, nil
}

func parsedPath(parsed *url.URL) string {
	if parsed == nil {
		return ""
	}
	return parsed.Path
}

func strictIdentitySecurityVaultNamespace(raw string) (string, error) {
	if raw == "" {
		return "", nil
	}
	if raw != strings.TrimSpace(raw) ||
		!identitySecurityVaultNamespacePattern.MatchString(raw) {
		return "", errors.New("identity security Vault namespace is invalid")
	}
	return strings.TrimSuffix(raw, "/"), nil
}

func validIdentitySecurityVaultRecordToken(value string) bool {
	if !identitySecurityVaultRecordTokenPattern.MatchString(value) {
		return false
	}
	decoded, err := base64.RawURLEncoding.Strict().DecodeString(value)
	return err == nil && len(decoded) == sha256DigestBytes
}

const sha256DigestBytes = 32

func validIdentitySecurityVaultToken(token []byte) bool {
	return len(token) >= 16 && len(token) <= 4096 &&
		identitySecurityVaultTokenPattern.Match(token)
}

type identitySecurityVaultCancelOnCloseBody struct {
	io.ReadCloser
	cancel context.CancelFunc
}

func (body *identitySecurityVaultCancelOnCloseBody) Close() error {
	if body == nil || body.ReadCloser == nil {
		return nil
	}
	err := body.ReadCloser.Close()
	if body.cancel != nil {
		body.cancel()
		body.cancel = nil
	}
	return err
}

func decodeIdentitySecurityVaultJSONResponse(
	response *http.Response,
	target any,
) error {
	if response == nil || response.Body == nil {
		return ErrIdentitySecurityProcessorUnavailable
	}
	mediaType, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		drainIdentitySecurityVaultResponse(response.Body)
		return ErrIdentitySecurityProcessorUnavailable
	}
	body, err := io.ReadAll(
		io.LimitReader(response.Body, maxIdentitySecurityVaultResponseBytes+1),
	)
	if err != nil || len(body) > maxIdentitySecurityVaultResponseBytes {
		clear(body)
		return ErrIdentitySecurityProcessorUnavailable
	}
	defer clear(body)
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return ErrIdentitySecurityProcessorUnavailable
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return ErrIdentitySecurityProcessorUnavailable
	}
	return nil
}

func drainIdentitySecurityVaultResponse(body io.Reader) {
	if body == nil {
		return
	}
	_, _ = io.Copy(
		io.Discard,
		io.LimitReader(body, maxIdentitySecurityVaultResponseBytes),
	)
}

func safeIdentitySecurityVaultHTTPError(err error) error {
	switch {
	case errors.Is(err, context.DeadlineExceeded):
		return fmt.Errorf(
			"identity security Vault request timed out: %w",
			context.DeadlineExceeded,
		)
	case errors.Is(err, context.Canceled):
		return fmt.Errorf(
			"identity security Vault request canceled: %w",
			context.Canceled,
		)
	default:
		return ErrIdentitySecurityProcessorUnavailable
	}
}

var (
	_ IdentitySecurityVaultTokenProvider = FileIdentitySecurityVaultTokenProvider{}
	_ IdentitySecurityProcessorVault     = (*HashiCorpVaultKVV2IdentitySecurityProcessorVault)(
		nil,
	)
	_ IdentitySecurityProcessorKeyResolver = (*HashiCorpVaultKVV2IdentitySecurityProcessorKeyResolver)(
		nil,
	)
)
