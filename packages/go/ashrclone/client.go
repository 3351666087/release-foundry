package ashrclone

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

const DefaultBaseURL = "https://api.ashr.local/v1/"

type Client struct {
	BaseURL    string
	APIKey     string
	HTTPClient *http.Client
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

func NewClient(options ...ClientOption) *Client {
	client := &Client{BaseURL: normalizeBaseURL(DefaultBaseURL), HTTPClient: &http.Client{Timeout: 30 * time.Second}}
	for _, option := range options {
		option(client)
	}
	return client
}

func NewClientFromEnv(options ...ClientOption) *Client {
	client := NewClient(options...)
	if client.APIKey == "" {
		client.APIKey = os.Getenv("ASHR_API_KEY")
	}
	if client.APIKey == "" {
		client.APIKey = os.Getenv("ASHR_LABS_API_KEY")
	}
	if envBaseURL := os.Getenv("ASHR_LABS_BASE_URL"); envBaseURL != "" {
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
	payload, err := json.Marshal(requestBody)
	if err != nil {
		return err
	}
	endpoint, err := url.JoinPath(client.BaseURL, strings.TrimPrefix(path, "/"))
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(payload))
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

	httpClient := client.HTTPClient
	if httpClient == nil {
		httpClient = http.DefaultClient
	}
	resp, err := httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("ashr API returned status %d: %s", resp.StatusCode, string(body))
	}
	if responseBody == nil || len(body) == 0 {
		return nil
	}
	return json.Unmarshal(body, responseBody)
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
