package releasefoundry

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
)

type APIError struct {
	StatusCode int
	Message    string
	Response   JSONMap
	Headers    JSONMap
	ErrorKind  string
}

type NotFoundError struct {
	Resource string
}

type QuotaExceededError struct {
	Operation string
	Limit     int
	Used      int
	Requested int
}

type QuotaExceededErrorSchema struct {
	Code      string `json:"code"`
	Message   string `json:"message"`
	Operation string `json:"operation"`
	Meter     string `json:"meter"`
	Unit      string `json:"unit"`
	Limit     int    `json:"limit"`
	Used      int    `json:"used"`
	Requested int    `json:"requested"`
	Remaining int    `json:"remaining"`
}

func (err NotFoundError) Error() string {
	if strings.TrimSpace(err.Resource) == "" {
		return "resource not found"
	}
	return err.Resource + " not found"
}

func (err QuotaExceededError) Error() string {
	detail := err.PublicSchema()
	return fmt.Sprintf("quota exceeded for %s: requested %d, remaining %d", detail.Operation, detail.Requested, detail.Remaining)
}

func (err QuotaExceededError) PublicSchema() QuotaExceededErrorSchema {
	remaining := err.Limit - err.Used
	if remaining < 0 {
		remaining = 0
	}
	requested := err.Requested
	if requested <= 0 {
		requested = 1
	}
	operation := NormalizeQuotaOperation(err.Operation)
	meter, _ := OperationMeterFor(operation)
	return QuotaExceededErrorSchema{
		Code:      "quota_exceeded",
		Message:   fmt.Sprintf("quota exceeded for %s: requested %d, remaining %d", operation, requested, remaining),
		Operation: operation,
		Meter:     meter.Meter,
		Unit:      meter.Unit,
		Limit:     err.Limit,
		Used:      err.Used,
		Requested: requested,
		Remaining: remaining,
	}
}

func NewAPIError(statusCode int, body []byte, headers http.Header) APIError {
	response := JSONMap{}
	if len(body) > 0 {
		var parsed any
		if err := json.Unmarshal(body, &parsed); err == nil {
			if mapped, ok := RedactSensitive(parsed).(map[string]any); ok {
				response = JSONMap(mapped)
			}
		}
	}
	message := errorMessage(response, statusCode, body)
	return APIError{StatusCode: statusCode, Message: message, Response: response, Headers: selectedHeaders(headers), ErrorKind: "http"}
}

func (err APIError) Error() string {
	return fmt.Sprintf("releasefoundry API returned status %d: %s", err.StatusCode, RedactSensitive(err.Message))
}

func (err APIError) Retryable() bool {
	return err.StatusCode == http.StatusTooManyRequests || err.StatusCode == http.StatusRequestTimeout || err.StatusCode >= 500
}

func errorMessage(response JSONMap, statusCode int, body []byte) string {
	for _, key := range []string{"message", "error", "detail"} {
		if value, ok := response[key].(string); ok && strings.TrimSpace(value) != "" {
			return value
		}
	}
	if len(body) > 0 {
		return string(RedactSensitive(string(body)).(string))
	}
	return fmt.Sprintf("HTTP %d", statusCode)
}

func selectedHeaders(headers http.Header) JSONMap {
	output := JSONMap{}
	for _, key := range []string{"Retry-After", "X-Request-ID", "X-RateLimit-Remaining", "X-RateLimit-Reset"} {
		if value := headers.Get(key); value != "" {
			output[strings.ToLower(strings.ReplaceAll(key, "-", "_"))] = value
		}
	}
	return output
}
