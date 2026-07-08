package ashrclone

import "fmt"

type IdempotencyOptions struct {
	Key       string `json:"idempotency_key,omitempty"`
	RequestID string `json:"request_id,omitempty"`
	APIKeyID  string `json:"api_key_id,omitempty"`
}

type IdempotencyConflictError struct {
	Operation string
	Key       string
}

func (err IdempotencyConflictError) Error() string {
	return fmt.Sprintf("idempotency conflict for %s with key %q", err.Operation, err.Key)
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
