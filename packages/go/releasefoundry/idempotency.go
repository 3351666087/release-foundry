package releasefoundry

import "fmt"

type IdempotencyOptions struct {
	Key                          string `json:"idempotency_key,omitempty"`
	RequestID                    string `json:"request_id,omitempty"`
	APIKeyID                     string `json:"api_key_id,omitempty"`
	AllowRetryWithoutIdempotency bool   `json:"allow_retry_without_idempotency,omitempty"`
}

type IdempotencyConflictError struct {
	Operation string
	Key       string
}

func (err IdempotencyConflictError) Error() string {
	return fmt.Sprintf("idempotency conflict for %s with key %q", err.Operation, err.Key)
}

type RetrySafetyError struct {
	Method string
	Path   string
}

func (err RetrySafetyError) Error() string {
	return fmt.Sprintf("refusing to retry mutating %s %s without idempotency key", err.Method, err.Path)
}

type Envelope[T any] struct {
	Operation        string `json:"operation"`
	Status           string `json:"status"`
	IdempotentReplay bool   `json:"idempotent_replay,omitempty"`
	Result           T      `json:"result"`
}

type idemRecord struct {
	Fingerprint string
	Response    any
}
