package ashrclone

import (
	"errors"
	"fmt"
	"time"
)

const (
	ProviderDispatchPending       = "pending"
	ProviderDispatchClaimed       = "claimed"
	ProviderDispatchIndeterminate = "indeterminate"
	ProviderDispatchReconciling   = "reconciling"
	ProviderDispatchCompleted     = "completed"
	ProviderDispatchFailed        = "failed"
	ProviderDispatchCancelled     = "cancelled"
)

var (
	ErrProviderDispatchConflict      = errors.New("provider dispatch conflict")
	ErrProviderDispatchFence         = errors.New("provider dispatch lease or fencing token rejected")
	ErrProviderDispatchCancelled     = errors.New("provider_dispatch_cancelled")
	ErrProviderDispatchDeadline      = errors.New("provider_dispatch_deadline")
	ErrProviderDispatchContention    = errors.New("provider_dispatch_contention")
	ErrProviderDispatchUnavailable   = errors.New("provider_dispatch_unavailable")
	ErrProviderDispatchIndeterminate = errors.New("provider_dispatch_indeterminate")
)

type ProviderDispatch struct {
	SchemaVersion          string     `json:"schema_version"`
	TenantID               string     `json:"tenant_id"`
	ProjectID              string     `json:"project_id"`
	DispatchID             string     `json:"dispatch_id"`
	Provider               string     `json:"provider"`
	Operation              string     `json:"operation"`
	RequestFingerprint     string     `json:"request_fingerprint"`
	Status                 string     `json:"status"`
	Attempts               int        `json:"attempts"`
	FencingToken           int64      `json:"fencing_token"`
	LeaseOwnerID           string     `json:"lease_owner_id,omitempty"`
	LeaseExpiresAt         *time.Time `json:"lease_expires_at,omitempty"`
	ProviderRequestID      string     `json:"provider_request_id,omitempty"`
	StreamObserved         bool       `json:"stream_observed"`
	StreamObservedSHA256   string     `json:"stream_observed_sha256,omitempty"`
	StreamObservedFence    *int64     `json:"stream_observed_fencing_token,omitempty"`
	StreamObservedAt       *time.Time `json:"stream_observed_at,omitempty"`
	TerminalProofSHA256    string     `json:"terminal_proof_sha256,omitempty"`
	TerminalResponseSHA256 string     `json:"terminal_response_sha256,omitempty"`
	ReconciliationReason   string     `json:"reconciliation_reason,omitempty"`
	ReconciliationAttempts int        `json:"reconciliation_attempts"`
	NextReconcileAt        *time.Time `json:"next_reconcile_at,omitempty"`
	LastErrorSHA256        string     `json:"last_error_sha256,omitempty"`
	CreatedAt              time.Time  `json:"created_at"`
	UpdatedAt              time.Time  `json:"updated_at"`
	ClaimedAt              *time.Time `json:"claimed_at,omitempty"`
	CompletedAt            *time.Time `json:"completed_at,omitempty"`
	FailedAt               *time.Time `json:"failed_at,omitempty"`
	RawPayloadIncluded     bool       `json:"raw_payload_included"`
}

type ProviderDispatchClaim struct {
	SchemaVersion string            `json:"schema_version"`
	Status        string            `json:"status"`
	Claimed       bool              `json:"claimed"`
	Dispatch      *ProviderDispatch `json:"dispatch,omitempty"`
}

type SubmitProviderDispatchOptions struct {
	DispatchID string
}

type ClaimProviderDispatchOptions struct {
	Provider     string
	Operation    string
	LeaseSeconds int
}

type CompleteProviderDispatchOptions struct {
	ProviderRequestID string
	Proof             JSONMap
	Response          JSONMap
}

type ObserveProviderDispatchStreamOptions struct {
	Stream JSONMap
}

type ReconcileProviderDispatchOptions struct {
	LeaseSeconds int
}

type ProviderDispatchConflictError struct {
	DispatchID           string
	ExistingFingerprint  string
	RequestedFingerprint string
}

func (err *ProviderDispatchConflictError) Error() string {
	return fmt.Sprintf("%v: dispatch %q already belongs to fingerprint %q, not %q",
		ErrProviderDispatchConflict, err.DispatchID, err.ExistingFingerprint, err.RequestedFingerprint)
}

func (err *ProviderDispatchConflictError) Unwrap() error { return ErrProviderDispatchConflict }

type ProviderDispatchFenceError struct {
	DispatchID   string
	LeaseOwnerID string
	FencingToken int64
}

func (err *ProviderDispatchFenceError) Error() string {
	return fmt.Sprintf("%v: dispatch %q owner=%q fence=%d",
		ErrProviderDispatchFence, err.DispatchID, err.LeaseOwnerID, err.FencingToken)
}

func (err *ProviderDispatchFenceError) Unwrap() error { return ErrProviderDispatchFence }
