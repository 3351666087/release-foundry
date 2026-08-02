package releasefoundry

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

const DefaultBaseURL = "https://api.releasefoundry.example/testing-platform-api"

type Client struct {
	BaseURL      string
	APIKey       string
	HTTPClient   *http.Client
	MaxRetries   int
	RetryBackoff time.Duration
	RetrySleeper func(context.Context, time.Duration) error
}

type ClientOption func(*Client)

func WithBaseURL(baseURL string) ClientOption {
	return func(client *Client) { client.BaseURL = normalizeBaseURL(baseURL) }
}

func WithAPIKey(apiKey string) ClientOption {
	return func(client *Client) { client.APIKey = apiKey }
}

func WithHTTPClient(httpClient *http.Client) ClientOption {
	return func(client *Client) {
		if httpClient != nil {
			client.HTTPClient = httpClient
		}
	}
}

func WithRetry(maxRetries int, backoff time.Duration) ClientOption {
	return func(client *Client) {
		if maxRetries < 0 {
			maxRetries = 0
		}
		client.MaxRetries = maxRetries
		if backoff >= 0 {
			client.RetryBackoff = backoff
		}
	}
}

func WithRetrySleeper(sleeper func(context.Context, time.Duration) error) ClientOption {
	return func(client *Client) {
		if sleeper != nil {
			client.RetrySleeper = sleeper
		}
	}
}

func NewClient(options ...ClientOption) *Client {
	client := &Client{BaseURL: normalizeBaseURL(DefaultBaseURL), HTTPClient: &http.Client{Timeout: 30 * time.Second}, MaxRetries: 2, RetryBackoff: 500 * time.Millisecond, RetrySleeper: sleepContext}
	for _, option := range options {
		option(client)
	}
	return client
}

func NewClientFromEnv(options ...ClientOption) *Client {
	client := NewClient(options...)
	if client.APIKey == "" {
		client.APIKey = os.Getenv("RELEASEFOUNDRY_API_KEY")
	}
	if client.APIKey == "" {
		client.APIKey = os.Getenv("RELEASEFOUNDRY_API_KEY")
	}
	if envBaseURL := os.Getenv("RELEASEFOUNDRY_BASE_URL"); envBaseURL != "" {
		client.BaseURL = normalizeBaseURL(envBaseURL)
	}
	return client
}

func (client *Client) RedactedConfig() JSONMap {
	apiKey := ""
	if client.APIKey != "" {
		apiKey = Redacted
	}
	return JSONMap{"base_url": client.BaseURL, "api_key": apiKey, "client_version": SaaSClientVersion}
}

func (client *Client) Post(ctx context.Context, path string, requestBody any, responseBody any, options IdempotencyOptions) error {
	return client.DoJSON(ctx, http.MethodPost, path, requestBody, responseBody, options)
}

func (client *Client) Get(ctx context.Context, path string, requestBody any, responseBody any, options IdempotencyOptions) error {
	return client.DoJSON(ctx, http.MethodGet, path, requestBody, responseBody, options)
}

func (client *Client) DoJSON(ctx context.Context, method, path string, requestBody any, responseBody any, options IdempotencyOptions) error {
	payload, err := json.Marshal(requestBody)
	if err != nil {
		return err
	}
	endpoint, err := url.JoinPath(client.BaseURL, strings.TrimPrefix(path, "/"))
	if err != nil {
		return err
	}
	if method == "" {
		method = http.MethodPost
	}
	maxRetries := client.MaxRetries
	if !options.AllowRetryWithoutIdempotency && maxRetries > 0 && requestMutates(method) && options.Key == "" {
		return RetrySafetyError{Method: method, Path: path}
	}
	httpClient := client.HTTPClient
	if httpClient == nil {
		httpClient = http.DefaultClient
	}
	var lastErr error
	for attempt := 0; attempt <= maxRetries; attempt++ {
		req, err := http.NewRequestWithContext(ctx, method, endpoint, bytes.NewReader(payload))
		if err != nil {
			return err
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Accept", "application/json")
		if client.APIKey != "" {
			req.Header.Set("Authorization", "Bearer "+client.APIKey)
		}
		if options.Key != "" {
			req.Header.Set("Idempotency-Key", options.Key)
		}
		if options.RequestID != "" {
			req.Header.Set("X-Request-ID", options.RequestID)
		}
		resp, err := httpClient.Do(req)
		if err != nil {
			lastErr = err
			if !isRetryableTransportError(err) || attempt >= maxRetries {
				return err
			}
		} else {
			body, readErr := readAndClose(resp)
			if readErr != nil {
				return readErr
			}
			if resp.StatusCode < 200 || resp.StatusCode >= 300 {
				apiErr := NewAPIError(resp.StatusCode, body, resp.Header)
				lastErr = apiErr
				if !apiErr.Retryable() || attempt >= maxRetries {
					return apiErr
				}
			} else {
				if responseBody == nil || len(body) == 0 {
					return nil
				}
				return json.Unmarshal(body, responseBody)
			}
		}
		if err := client.sleep(ctx, attempt); err != nil {
			return err
		}
	}
	if lastErr != nil {
		return lastErr
	}
	return errors.New("releasefoundry API request failed without a response")
}

func readAndClose(resp *http.Response) ([]byte, error) {
	defer resp.Body.Close()
	return io.ReadAll(resp.Body)
}

func requestMutates(method string) bool {
	switch strings.ToUpper(method) {
	case http.MethodGet, http.MethodHead, http.MethodOptions:
		return false
	default:
		return true
	}
}

func isRetryableTransportError(err error) bool {
	return err != nil
}

func (client *Client) sleep(ctx context.Context, attempt int) error {
	if client.RetryBackoff <= 0 {
		return nil
	}
	delay := client.RetryBackoff * time.Duration(1<<attempt)
	sleeper := client.RetrySleeper
	if sleeper == nil {
		sleeper = sleepContext
	}
	return sleeper(ctx, delay)
}

func sleepContext(ctx context.Context, delay time.Duration) error {
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

func normalizeBaseURL(baseURL string) string {
	if strings.TrimSpace(baseURL) == "" {
		baseURL = DefaultBaseURL
	}
	if !strings.HasSuffix(baseURL, "/") {
		baseURL += "/"
	}
	return baseURL
}
