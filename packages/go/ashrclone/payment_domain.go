package ashrclone

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"reflect"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
	"unicode"
)

const PaymentDomainSchemaVersion = "ashr.clone.payment_domain.v1"
const PaymentVerificationArtifactSchemaVersion = "ashr.clone.payment_verification_artifact.v1"

const (
	PaymentProviderStripe           = "stripe"
	PaymentProviderWeChatPay        = "wechat_pay"
	PaymentProviderAlipay           = "alipay"
	PaymentProviderDomesticBankCard = "domestic_bank_card"

	PaymentOrderStatusCreated   = "created"
	PaymentOrderStatusPending   = "pending"
	PaymentOrderStatusSucceeded = "succeeded"
	PaymentOrderStatusClosed    = "closed"
	PaymentOrderStatusFailed    = "failed"

	PaymentRefundStatusCreated    = "created"
	PaymentRefundStatusProcessing = "processing"
	PaymentRefundStatusSucceeded  = "succeeded"
	PaymentRefundStatusClosed     = "closed"
	PaymentRefundStatusFailed     = "failed"

	PaymentBillMatchMatched   = "matched"
	PaymentBillMatchUnmatched = "unmatched"
	PaymentBillMatchConflict  = "conflict"
)

const PaymentDomainSchemaSQL = `
CREATE TABLE IF NOT EXISTS ashr_payment_orders (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    merchant_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    merchant_order_id TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    record_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, project_id, merchant_id, provider, merchant_order_id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES ashr_projects(tenant_id, project_id) ON DELETE CASCADE,
    CONSTRAINT ashr_payment_order_request_hash CHECK (request_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE TABLE IF NOT EXISTS ashr_payment_refunds (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    merchant_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    merchant_refund_id TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    record_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, project_id, merchant_id, provider, merchant_refund_id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES ashr_projects(tenant_id, project_id) ON DELETE CASCADE,
    CONSTRAINT ashr_payment_refund_request_hash CHECK (request_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE TABLE IF NOT EXISTS ashr_payment_notifications (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    merchant_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_event_id TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    headers_sha256 TEXT NOT NULL DEFAULT '',
    record_json JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, project_id, merchant_id, provider, provider_event_id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES ashr_projects(tenant_id, project_id) ON DELETE CASCADE,
    CONSTRAINT ashr_payment_notification_payload_hash CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ashr_payment_notification_headers_hash CHECK (headers_sha256 = '' OR headers_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE TABLE IF NOT EXISTS ashr_payment_bill_entries (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    merchant_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    bill_entry_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    record_json JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, project_id, merchant_id, provider, bill_entry_id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES ashr_projects(tenant_id, project_id) ON DELETE CASCADE,
    CONSTRAINT ashr_payment_bill_source_hash CHECK (source_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS ashr_payment_orders_scope_idx
    ON ashr_payment_orders (tenant_id, project_id, merchant_id, provider, created_at, merchant_order_id);
CREATE INDEX IF NOT EXISTS ashr_payment_refunds_scope_idx
    ON ashr_payment_refunds (tenant_id, project_id, merchant_id, provider, created_at, merchant_refund_id);
CREATE INDEX IF NOT EXISTS ashr_payment_notifications_scope_idx
    ON ashr_payment_notifications (tenant_id, project_id, merchant_id, provider, received_at, provider_event_id);
CREATE INDEX IF NOT EXISTS ashr_payment_bill_entries_scope_idx
    ON ashr_payment_bill_entries (tenant_id, project_id, merchant_id, provider, received_at, bill_entry_id);
`

type PaymentProviderCapabilities struct {
	SchemaVersion         string            `json:"schema_version"`
	Provider              string            `json:"provider"`
	DisplayName           string            `json:"display_name"`
	OrderStatuses         []string          `json:"order_statuses"`
	RefundStatuses        []string          `json:"refund_statuses"`
	NotificationResources []string          `json:"notification_resources"`
	Channels              []string          `json:"channels"`
	BillKinds             []string          `json:"bill_kinds"`
	Capabilities          map[string]bool   `json:"capabilities"`
	ProviderStatusMap     map[string]string `json:"provider_status_map"`
	RefundStatusMap       map[string]string `json:"refund_status_map"`
}

type PaymentProviderCapabilityList struct {
	SchemaVersion string                        `json:"schema_version"`
	Providers     []PaymentProviderCapabilities `json:"providers"`
	Count         int                           `json:"count"`
}

type PaymentOrderReceive struct {
	Provider                    string  `json:"provider"`
	MerchantID                  string  `json:"merchant_id"`
	MerchantOrderID             string  `json:"merchant_order_id"`
	Amount                      int64   `json:"amount"`
	Currency                    string  `json:"currency"`
	Description                 string  `json:"description,omitempty"`
	Channel                     string  `json:"channel,omitempty"`
	CustomerRef                 string  `json:"customer_ref,omitempty"`
	AcquirerReference           string  `json:"acquirer_reference,omitempty"`
	PaymentMethodTokenReference string  `json:"payment_method_token_reference,omitempty"`
	Metadata                    JSONMap `json:"metadata,omitempty"`
}

type PaymentOrder struct {
	SchemaVersion               string     `json:"schema_version"`
	TenantID                    string     `json:"tenant_id"`
	ProjectID                   string     `json:"project_id"`
	MerchantID                  string     `json:"merchant_id"`
	Provider                    string     `json:"provider"`
	MerchantOrderID             string     `json:"merchant_order_id"`
	ProviderOrderID             string     `json:"provider_order_id,omitempty"`
	Amount                      int64      `json:"amount"`
	Currency                    string     `json:"currency"`
	Description                 string     `json:"description,omitempty"`
	Channel                     string     `json:"channel,omitempty"`
	CustomerRef                 string     `json:"customer_ref,omitempty"`
	AcquirerReference           string     `json:"acquirer_reference,omitempty"`
	PaymentMethodTokenReference string     `json:"payment_method_token_reference,omitempty"`
	Status                      string     `json:"status"`
	ProviderStatus              string     `json:"provider_status,omitempty"`
	Metadata                    JSONMap    `json:"metadata,omitempty"`
	RequestSHA256               string     `json:"request_sha256"`
	RawPayloadIncluded          bool       `json:"raw_payload_included"`
	SecretValuePresent          bool       `json:"secret_value_present"`
	CreatedAt                   time.Time  `json:"created_at"`
	UpdatedAt                   time.Time  `json:"updated_at"`
	SucceededAt                 *time.Time `json:"succeeded_at,omitempty"`
	ClosedAt                    *time.Time `json:"closed_at,omitempty"`
	FailedAt                    *time.Time `json:"failed_at,omitempty"`
}

type PaymentOrderList struct {
	SchemaVersion string         `json:"schema_version"`
	TenantID      string         `json:"tenant_id"`
	ProjectID     string         `json:"project_id"`
	MerchantID    string         `json:"merchant_id,omitempty"`
	Provider      string         `json:"provider,omitempty"`
	Status        string         `json:"status,omitempty"`
	Orders        []PaymentOrder `json:"orders"`
	Count         int            `json:"count"`
}

type PaymentRefundReceive struct {
	Provider         string  `json:"provider"`
	MerchantID       string  `json:"merchant_id"`
	MerchantRefundID string  `json:"merchant_refund_id"`
	MerchantOrderID  string  `json:"merchant_order_id"`
	Amount           int64   `json:"amount"`
	Currency         string  `json:"currency"`
	Reason           string  `json:"reason,omitempty"`
	Metadata         JSONMap `json:"metadata,omitempty"`
}

type PaymentRefund struct {
	SchemaVersion      string     `json:"schema_version"`
	TenantID           string     `json:"tenant_id"`
	ProjectID          string     `json:"project_id"`
	MerchantID         string     `json:"merchant_id"`
	Provider           string     `json:"provider"`
	MerchantRefundID   string     `json:"merchant_refund_id"`
	ProviderRefundID   string     `json:"provider_refund_id,omitempty"`
	MerchantOrderID    string     `json:"merchant_order_id"`
	Amount             int64      `json:"amount"`
	Currency           string     `json:"currency"`
	Reason             string     `json:"reason,omitempty"`
	Status             string     `json:"status"`
	ProviderStatus     string     `json:"provider_status,omitempty"`
	Metadata           JSONMap    `json:"metadata,omitempty"`
	RequestSHA256      string     `json:"request_sha256"`
	RawPayloadIncluded bool       `json:"raw_payload_included"`
	SecretValuePresent bool       `json:"secret_value_present"`
	CreatedAt          time.Time  `json:"created_at"`
	UpdatedAt          time.Time  `json:"updated_at"`
	SucceededAt        *time.Time `json:"succeeded_at,omitempty"`
	ClosedAt           *time.Time `json:"closed_at,omitempty"`
	FailedAt           *time.Time `json:"failed_at,omitempty"`
}

type PaymentRefundList struct {
	SchemaVersion string          `json:"schema_version"`
	TenantID      string          `json:"tenant_id"`
	ProjectID     string          `json:"project_id"`
	MerchantID    string          `json:"merchant_id,omitempty"`
	Provider      string          `json:"provider,omitempty"`
	Status        string          `json:"status,omitempty"`
	Refunds       []PaymentRefund `json:"refunds"`
	Count         int             `json:"count"`
}

type PaymentNotificationReceive struct {
	Provider         string    `json:"provider"`
	MerchantID       string    `json:"merchant_id"`
	ProviderEventID  string    `json:"provider_event_id"`
	EventType        string    `json:"event_type"`
	ResourceType     string    `json:"resource_type"`
	MerchantOrderID  string    `json:"merchant_order_id,omitempty"`
	MerchantRefundID string    `json:"merchant_refund_id,omitempty"`
	ProviderObjectID string    `json:"provider_object_id,omitempty"`
	ProviderStatus   string    `json:"provider_status"`
	PayloadSHA256    string    `json:"payload_sha256"`
	HeadersSHA256    string    `json:"headers_sha256,omitempty"`
	OccurredAt       time.Time `json:"occurred_at,omitempty"`
}

type PaymentVerificationArtifact struct {
	SchemaVersion      string    `json:"schema_version"`
	VerifierID         string    `json:"verifier_id"`
	VerifierVersion    string    `json:"verifier_version"`
	Provider           string    `json:"provider"`
	MerchantID         string    `json:"merchant_id"`
	AcquirerReference  string    `json:"acquirer_reference,omitempty"`
	ProviderEventID    string    `json:"provider_event_id"`
	RawBodySHA256      string    `json:"raw_body_sha256"`
	SignatureSHA256    string    `json:"signature_sha256"`
	VerifiedAt         time.Time `json:"verified_at"`
	ProviderTimestamp  string    `json:"provider_timestamp,omitempty"`
	ProviderNonce      string    `json:"provider_nonce,omitempty"`
	CertificateKeyRef  string    `json:"certificate_key_ref"`
	ArtifactMACSHA256  string    `json:"artifact_mac_sha256"`
	RawPayloadIncluded bool      `json:"raw_payload_included"`
	SecretValuePresent bool      `json:"secret_value_present"`
}

type paymentVerificationEvidence struct {
	VerifierID        string
	VerifierVersion   string
	AcquirerReference string
	SignatureSHA256   string
	VerifiedAt        time.Time
	ProviderTimestamp string
	ProviderNonce     string
	CertificateKeyRef string
}

type sealedPaymentNotification struct {
	request  PaymentNotificationReceive
	artifact PaymentVerificationArtifact
	mac      [sha256.Size]byte
}

type PaymentNotification struct {
	SchemaVersion      string                      `json:"schema_version"`
	TenantID           string                      `json:"tenant_id"`
	ProjectID          string                      `json:"project_id"`
	MerchantID         string                      `json:"merchant_id"`
	Provider           string                      `json:"provider"`
	ProviderEventID    string                      `json:"provider_event_id"`
	EventType          string                      `json:"event_type"`
	ResourceType       string                      `json:"resource_type"`
	MerchantOrderID    string                      `json:"merchant_order_id,omitempty"`
	MerchantRefundID   string                      `json:"merchant_refund_id,omitempty"`
	ProviderObjectID   string                      `json:"provider_object_id,omitempty"`
	ProviderStatus     string                      `json:"provider_status"`
	NormalizedStatus   string                      `json:"normalized_status"`
	PayloadSHA256      string                      `json:"payload_sha256"`
	HeadersSHA256      string                      `json:"headers_sha256,omitempty"`
	Verification       PaymentVerificationArtifact `json:"verification"`
	Applied            bool                        `json:"applied"`
	RawPayloadIncluded bool                        `json:"raw_payload_included"`
	RawHeadersIncluded bool                        `json:"raw_headers_included"`
	SecretValuePresent bool                        `json:"secret_value_present"`
	OccurredAt         time.Time                   `json:"occurred_at"`
	ReceivedAt         time.Time                   `json:"received_at"`
}

type PaymentNotificationList struct {
	SchemaVersion string                `json:"schema_version"`
	TenantID      string                `json:"tenant_id"`
	ProjectID     string                `json:"project_id"`
	MerchantID    string                `json:"merchant_id,omitempty"`
	Provider      string                `json:"provider,omitempty"`
	Notifications []PaymentNotification `json:"notifications"`
	Count         int                   `json:"count"`
}

type PaymentBillEntryReceive struct {
	Provider         string    `json:"provider"`
	MerchantID       string    `json:"merchant_id"`
	BillEntryID      string    `json:"bill_entry_id"`
	BillDate         string    `json:"bill_date"`
	BillKind         string    `json:"bill_kind"`
	TransactionID    string    `json:"transaction_id,omitempty"`
	MerchantOrderID  string    `json:"merchant_order_id,omitempty"`
	MerchantRefundID string    `json:"merchant_refund_id,omitempty"`
	Amount           int64     `json:"amount"`
	Currency         string    `json:"currency"`
	ProviderStatus   string    `json:"provider_status"`
	SourceSHA256     string    `json:"source_sha256"`
	OccurredAt       time.Time `json:"occurred_at,omitempty"`
}

type PaymentBillEntry struct {
	SchemaVersion      string    `json:"schema_version"`
	TenantID           string    `json:"tenant_id"`
	ProjectID          string    `json:"project_id"`
	MerchantID         string    `json:"merchant_id"`
	Provider           string    `json:"provider"`
	BillEntryID        string    `json:"bill_entry_id"`
	BillDate           string    `json:"bill_date"`
	BillKind           string    `json:"bill_kind"`
	TransactionID      string    `json:"transaction_id,omitempty"`
	MerchantOrderID    string    `json:"merchant_order_id,omitempty"`
	MerchantRefundID   string    `json:"merchant_refund_id,omitempty"`
	Amount             int64     `json:"amount"`
	Currency           string    `json:"currency"`
	ProviderStatus     string    `json:"provider_status"`
	SourceSHA256       string    `json:"source_sha256"`
	MatchStatus        string    `json:"match_status"`
	MatchReason        string    `json:"match_reason,omitempty"`
	RawPayloadIncluded bool      `json:"raw_payload_included"`
	SecretValuePresent bool      `json:"secret_value_present"`
	OccurredAt         time.Time `json:"occurred_at"`
	ReceivedAt         time.Time `json:"received_at"`
}

type PaymentBillEntryList struct {
	SchemaVersion string             `json:"schema_version"`
	TenantID      string             `json:"tenant_id"`
	ProjectID     string             `json:"project_id"`
	MerchantID    string             `json:"merchant_id,omitempty"`
	Provider      string             `json:"provider,omitempty"`
	MatchStatus   string             `json:"match_status,omitempty"`
	Entries       []PaymentBillEntry `json:"entries"`
	Count         int                `json:"count"`
}

type PaymentDomainConflictError struct {
	Resource string
	Provider string
	ID       string
}

func (err PaymentDomainConflictError) Error() string {
	return fmt.Sprintf("payment %s conflict for provider %q id %q", err.Resource, err.Provider, err.ID)
}

type PaymentNotificationVerificationRequiredError struct{}

func (PaymentNotificationVerificationRequiredError) Error() string {
	return "payment notification requires a trusted internal provider verification artifact"
}

type paymentDomainRepository interface {
	receiveOrder(context.Context, PaymentOrder) (PaymentOrder, bool, error)
	getOrder(context.Context, string, string, string, string, string) (PaymentOrder, error)
	listOrders(context.Context, string, string, string, string, string, int) (PaymentOrderList, error)
	receiveRefund(context.Context, PaymentRefund) (PaymentRefund, bool, error)
	getRefund(context.Context, string, string, string, string, string) (PaymentRefund, error)
	listRefunds(context.Context, string, string, string, string, string, int) (PaymentRefundList, error)
	receiveNotification(context.Context, PaymentNotification) (PaymentNotification, bool, error)
	getNotification(context.Context, string, string, string, string, string) (PaymentNotification, error)
	listNotifications(context.Context, string, string, string, string, int) (PaymentNotificationList, error)
	receiveBillEntry(context.Context, PaymentBillEntry) (PaymentBillEntry, bool, error)
	getBillEntry(context.Context, string, string, string, string, string) (PaymentBillEntry, error)
	listBillEntries(context.Context, string, string, string, string, string, int) (PaymentBillEntryList, error)
}

type PaymentDomainService struct {
	repository  paymentDomainRepository
	now         func() time.Time
	artifactKey [sha256.Size]byte
}

func NewPaymentDomainService(repository paymentDomainRepository) (*PaymentDomainService, error) {
	if repository == nil {
		return nil, fmt.Errorf("payment domain repository is required")
	}
	service := &PaymentDomainService{repository: repository, now: func() time.Time { return time.Now().UTC() }}
	if _, err := rand.Read(service.artifactKey[:]); err != nil {
		return nil, fmt.Errorf("initialize payment verification artifact key: %w", err)
	}
	return service, nil
}

func PaymentProviderCapability(provider string) (PaymentProviderCapabilities, error) {
	provider = normalizeChinaPaymentProvider(provider)
	profiles := paymentProviderProfiles()
	profile, ok := profiles[provider]
	if !ok {
		return PaymentProviderCapabilities{}, fmt.Errorf("unsupported payment provider %q", provider)
	}
	return clonePaymentProviderCapabilities(profile), nil
}

func PaymentProviderCapabilitiesList() PaymentProviderCapabilityList {
	profiles := paymentProviderProfiles()
	providers := make([]PaymentProviderCapabilities, 0, len(profiles))
	for _, provider := range []string{PaymentProviderAlipay, PaymentProviderDomesticBankCard, PaymentProviderStripe, PaymentProviderWeChatPay} {
		providers = append(providers, clonePaymentProviderCapabilities(profiles[provider]))
	}
	return PaymentProviderCapabilityList{SchemaVersion: PaymentDomainSchemaVersion, Providers: providers, Count: len(providers)}
}

func (service *PaymentDomainService) ReceiveOrder(ctx context.Context, tenantID, projectID string, request PaymentOrderReceive) (Envelope[PaymentOrder], error) {
	if err := validatePaymentScope(tenantID, projectID); err != nil {
		return Envelope[PaymentOrder]{}, err
	}
	if err := rejectPaymentCardSecrets(request.Metadata); err != nil {
		return Envelope[PaymentOrder]{}, err
	}
	request = normalizePaymentOrderReceive(request)
	if err := validatePaymentOrderReceive(request); err != nil {
		return Envelope[PaymentOrder]{}, err
	}
	now := service.now().UTC()
	requestHash := mustFingerprint(request)
	order := publicPaymentOrder(PaymentOrder{
		SchemaVersion: PaymentDomainSchemaVersion, TenantID: tenantID, ProjectID: projectID,
		MerchantID: request.MerchantID, Provider: request.Provider, MerchantOrderID: request.MerchantOrderID, Amount: request.Amount,
		Currency: request.Currency, Description: request.Description, Channel: request.Channel,
		CustomerRef: request.CustomerRef, AcquirerReference: request.AcquirerReference,
		PaymentMethodTokenReference: request.PaymentMethodTokenReference,
		Status:                      PaymentOrderStatusCreated, Metadata: request.Metadata,
		RequestSHA256: requestHash, CreatedAt: now, UpdatedAt: now,
	})
	stored, replay, err := service.repository.receiveOrder(ctx, order)
	if err != nil {
		return Envelope[PaymentOrder]{}, err
	}
	return Envelope[PaymentOrder]{Operation: "payment.order.receive", Status: "ok", IdempotentReplay: replay, Result: publicPaymentOrder(stored)}, nil
}

func (service *PaymentDomainService) GetOrder(ctx context.Context, tenantID, projectID, merchantID, provider, merchantOrderID string) (Envelope[PaymentOrder], error) {
	if err := validatePaymentIdentity(tenantID, projectID, merchantID, provider, merchantOrderID, "merchant_order_id"); err != nil {
		return Envelope[PaymentOrder]{}, err
	}
	order, err := service.repository.getOrder(ctx, tenantID, projectID, strings.TrimSpace(merchantID), normalizeChinaPaymentProvider(provider), strings.TrimSpace(merchantOrderID))
	return Envelope[PaymentOrder]{Operation: "payment.order.get", Status: "ok", Result: publicPaymentOrder(order)}, err
}

func (service *PaymentDomainService) ListOrders(ctx context.Context, tenantID, projectID, merchantID, provider, status string, limit int) (Envelope[PaymentOrderList], error) {
	if err := validatePaymentScope(tenantID, projectID); err != nil {
		return Envelope[PaymentOrderList]{}, err
	}
	merchantID = strings.TrimSpace(merchantID)
	if merchantID == "" {
		return Envelope[PaymentOrderList]{}, fmt.Errorf("merchant_id is required")
	}
	provider, err := validateOptionalPaymentProvider(provider)
	if err != nil {
		return Envelope[PaymentOrderList]{}, err
	}
	status = strings.ToLower(strings.TrimSpace(status))
	if status != "" && !validPaymentOrderStatus(status) {
		return Envelope[PaymentOrderList]{}, fmt.Errorf("invalid payment order status %q", status)
	}
	result, err := service.repository.listOrders(ctx, tenantID, projectID, merchantID, provider, status, normalizePaymentListLimit(limit))
	return Envelope[PaymentOrderList]{Operation: "payment.order.list", Status: "ok", Result: result}, err
}

func (service *PaymentDomainService) ReceiveRefund(ctx context.Context, tenantID, projectID string, request PaymentRefundReceive) (Envelope[PaymentRefund], error) {
	if err := validatePaymentScope(tenantID, projectID); err != nil {
		return Envelope[PaymentRefund]{}, err
	}
	if err := rejectPaymentCardSecrets(request.Metadata); err != nil {
		return Envelope[PaymentRefund]{}, err
	}
	request = normalizePaymentRefundReceive(request)
	if err := validatePaymentRefundReceive(request); err != nil {
		return Envelope[PaymentRefund]{}, err
	}
	order, err := service.repository.getOrder(ctx, tenantID, projectID, request.MerchantID, request.Provider, request.MerchantOrderID)
	if err != nil {
		return Envelope[PaymentRefund]{}, err
	}
	if request.Currency != order.Currency || request.Amount > order.Amount {
		return Envelope[PaymentRefund]{}, fmt.Errorf("refund amount/currency exceeds or differs from the payment order")
	}
	now := service.now().UTC()
	refund := publicPaymentRefund(PaymentRefund{
		SchemaVersion: PaymentDomainSchemaVersion, TenantID: tenantID, ProjectID: projectID,
		MerchantID: request.MerchantID, Provider: request.Provider, MerchantRefundID: request.MerchantRefundID,
		MerchantOrderID: request.MerchantOrderID, Amount: request.Amount, Currency: request.Currency,
		Reason: request.Reason, Status: PaymentRefundStatusCreated, Metadata: request.Metadata,
		RequestSHA256: mustFingerprint(request), CreatedAt: now, UpdatedAt: now,
	})
	stored, replay, err := service.repository.receiveRefund(ctx, refund)
	if err != nil {
		return Envelope[PaymentRefund]{}, err
	}
	return Envelope[PaymentRefund]{Operation: "payment.refund.receive", Status: "ok", IdempotentReplay: replay, Result: publicPaymentRefund(stored)}, nil
}

func (service *PaymentDomainService) GetRefund(ctx context.Context, tenantID, projectID, merchantID, provider, merchantRefundID string) (Envelope[PaymentRefund], error) {
	if err := validatePaymentIdentity(tenantID, projectID, merchantID, provider, merchantRefundID, "merchant_refund_id"); err != nil {
		return Envelope[PaymentRefund]{}, err
	}
	refund, err := service.repository.getRefund(ctx, tenantID, projectID, strings.TrimSpace(merchantID), normalizeChinaPaymentProvider(provider), strings.TrimSpace(merchantRefundID))
	return Envelope[PaymentRefund]{Operation: "payment.refund.get", Status: "ok", Result: publicPaymentRefund(refund)}, err
}

func (service *PaymentDomainService) ListRefunds(ctx context.Context, tenantID, projectID, merchantID, provider, status string, limit int) (Envelope[PaymentRefundList], error) {
	if err := validatePaymentScope(tenantID, projectID); err != nil {
		return Envelope[PaymentRefundList]{}, err
	}
	merchantID = strings.TrimSpace(merchantID)
	if merchantID == "" {
		return Envelope[PaymentRefundList]{}, fmt.Errorf("merchant_id is required")
	}
	provider, err := validateOptionalPaymentProvider(provider)
	if err != nil {
		return Envelope[PaymentRefundList]{}, err
	}
	status = strings.ToLower(strings.TrimSpace(status))
	if status != "" && !validPaymentRefundStatus(status) {
		return Envelope[PaymentRefundList]{}, fmt.Errorf("invalid payment refund status %q", status)
	}
	result, err := service.repository.listRefunds(ctx, tenantID, projectID, merchantID, provider, status, normalizePaymentListLimit(limit))
	return Envelope[PaymentRefundList]{Operation: "payment.refund.list", Status: "ok", Result: result}, err
}

func (service *PaymentDomainService) ReceiveNotification(ctx context.Context, tenantID, projectID string, request PaymentNotificationReceive) (Envelope[PaymentNotification], error) {
	if err := validatePaymentScope(tenantID, projectID); err != nil {
		return Envelope[PaymentNotification]{}, err
	}
	return Envelope[PaymentNotification]{}, PaymentNotificationVerificationRequiredError{}
}

func (service *PaymentDomainService) issueVerifiedPaymentNotification(request PaymentNotificationReceive, evidence paymentVerificationEvidence) (sealedPaymentNotification, error) {
	request = normalizePaymentNotificationReceive(request)
	normalizedStatus, err := validateAndNormalizePaymentNotification(request)
	if err != nil {
		return sealedPaymentNotification{}, err
	}
	now := service.now().UTC()
	if request.OccurredAt.IsZero() {
		request.OccurredAt = now
	}
	evidence.VerifierID = strings.TrimSpace(evidence.VerifierID)
	evidence.VerifierVersion = strings.TrimSpace(evidence.VerifierVersion)
	evidence.AcquirerReference = strings.TrimSpace(evidence.AcquirerReference)
	evidence.SignatureSHA256 = strings.ToLower(strings.TrimSpace(evidence.SignatureSHA256))
	evidence.ProviderTimestamp = strings.TrimSpace(evidence.ProviderTimestamp)
	evidence.ProviderNonce = strings.TrimSpace(evidence.ProviderNonce)
	evidence.CertificateKeyRef = strings.TrimSpace(evidence.CertificateKeyRef)
	if evidence.VerifiedAt.IsZero() {
		evidence.VerifiedAt = now
	}
	evidence.VerifiedAt = evidence.VerifiedAt.UTC()
	if evidence.VerifierID == "" || evidence.VerifierVersion == "" || evidence.CertificateKeyRef == "" {
		return sealedPaymentNotification{}, fmt.Errorf("verifier_id, verifier_version, and certificate_key_ref are required")
	}
	if !paymentSHA256Pattern.MatchString(evidence.SignatureSHA256) {
		return sealedPaymentNotification{}, fmt.Errorf("signature_sha256 must be a lowercase SHA-256 digest")
	}
	if evidence.VerifiedAt.After(now.Add(5 * time.Minute)) {
		return sealedPaymentNotification{}, fmt.Errorf("verified_at cannot be in the future")
	}
	artifact := PaymentVerificationArtifact{
		SchemaVersion: PaymentVerificationArtifactSchemaVersion,
		VerifierID:    evidence.VerifierID, VerifierVersion: evidence.VerifierVersion,
		Provider: request.Provider, MerchantID: request.MerchantID, AcquirerReference: evidence.AcquirerReference,
		ProviderEventID: request.ProviderEventID, RawBodySHA256: request.PayloadSHA256,
		SignatureSHA256: evidence.SignatureSHA256, VerifiedAt: evidence.VerifiedAt,
		ProviderTimestamp: evidence.ProviderTimestamp, ProviderNonce: evidence.ProviderNonce,
		CertificateKeyRef: evidence.CertificateKeyRef,
	}
	mac := service.paymentVerificationArtifactMAC(request, artifact)
	artifact.ArtifactMACSHA256 = hex.EncodeToString(mac[:])
	_ = normalizedStatus
	return sealedPaymentNotification{request: request, artifact: artifact, mac: mac}, nil
}

func (service *PaymentDomainService) receiveVerifiedNotification(ctx context.Context, tenantID, projectID string, sealed sealedPaymentNotification) (Envelope[PaymentNotification], error) {
	if err := validatePaymentScope(tenantID, projectID); err != nil {
		return Envelope[PaymentNotification]{}, err
	}
	request := normalizePaymentNotificationReceive(sealed.request)
	normalizedStatus, err := validateAndNormalizePaymentNotification(request)
	if err != nil {
		return Envelope[PaymentNotification]{}, err
	}
	expectedMAC := service.paymentVerificationArtifactMAC(request, sealed.artifact)
	if !hmac.Equal(expectedMAC[:], sealed.mac[:]) ||
		!hmac.Equal([]byte(hex.EncodeToString(expectedMAC[:])), []byte(sealed.artifact.ArtifactMACSHA256)) {
		return Envelope[PaymentNotification]{}, PaymentNotificationVerificationRequiredError{}
	}
	if sealed.artifact.SchemaVersion != PaymentVerificationArtifactSchemaVersion ||
		sealed.artifact.Provider != request.Provider ||
		sealed.artifact.MerchantID != request.MerchantID ||
		sealed.artifact.ProviderEventID != request.ProviderEventID ||
		sealed.artifact.RawBodySHA256 != request.PayloadSHA256 ||
		sealed.artifact.RawPayloadIncluded || sealed.artifact.SecretValuePresent {
		return Envelope[PaymentNotification]{}, PaymentNotificationVerificationRequiredError{}
	}
	now := service.now().UTC()
	notification := publicPaymentNotification(PaymentNotification{
		SchemaVersion: PaymentDomainSchemaVersion, TenantID: tenantID, ProjectID: projectID,
		MerchantID: request.MerchantID, Provider: request.Provider, ProviderEventID: request.ProviderEventID, EventType: request.EventType,
		ResourceType: request.ResourceType, MerchantOrderID: request.MerchantOrderID,
		MerchantRefundID: request.MerchantRefundID, ProviderObjectID: request.ProviderObjectID,
		ProviderStatus: request.ProviderStatus, NormalizedStatus: normalizedStatus,
		PayloadSHA256: request.PayloadSHA256, HeadersSHA256: request.HeadersSHA256,
		Verification: sealed.artifact,
		OccurredAt:   request.OccurredAt.UTC(), ReceivedAt: now,
	})
	stored, replay, err := service.repository.receiveNotification(ctx, notification)
	if err != nil {
		return Envelope[PaymentNotification]{}, err
	}
	return Envelope[PaymentNotification]{Operation: "payment.notification.receive", Status: "ok", IdempotentReplay: replay, Result: publicPaymentNotification(stored)}, nil
}

func (service *PaymentDomainService) paymentVerificationArtifactMAC(request PaymentNotificationReceive, artifact PaymentVerificationArtifact) [sha256.Size]byte {
	payload := struct {
		Request  PaymentNotificationReceive
		Artifact PaymentVerificationArtifact
	}{Request: request, Artifact: artifact}
	payload.Artifact.ArtifactMACSHA256 = ""
	encoded, _ := json.Marshal(payload)
	mac := hmac.New(sha256.New, service.artifactKey[:])
	_, _ = mac.Write(encoded)
	var result [sha256.Size]byte
	copy(result[:], mac.Sum(nil))
	return result
}

func (service *PaymentDomainService) GetNotification(ctx context.Context, tenantID, projectID, merchantID, provider, eventID string) (Envelope[PaymentNotification], error) {
	if err := validatePaymentIdentity(tenantID, projectID, merchantID, provider, eventID, "provider_event_id"); err != nil {
		return Envelope[PaymentNotification]{}, err
	}
	event, err := service.repository.getNotification(ctx, tenantID, projectID, strings.TrimSpace(merchantID), normalizeChinaPaymentProvider(provider), strings.TrimSpace(eventID))
	return Envelope[PaymentNotification]{Operation: "payment.notification.get", Status: "ok", Result: publicPaymentNotification(event)}, err
}

func (service *PaymentDomainService) ListNotifications(ctx context.Context, tenantID, projectID, merchantID, provider string, limit int) (Envelope[PaymentNotificationList], error) {
	if err := validatePaymentScope(tenantID, projectID); err != nil {
		return Envelope[PaymentNotificationList]{}, err
	}
	merchantID = strings.TrimSpace(merchantID)
	if merchantID == "" {
		return Envelope[PaymentNotificationList]{}, fmt.Errorf("merchant_id is required")
	}
	provider, err := validateOptionalPaymentProvider(provider)
	if err != nil {
		return Envelope[PaymentNotificationList]{}, err
	}
	result, err := service.repository.listNotifications(ctx, tenantID, projectID, merchantID, provider, normalizePaymentListLimit(limit))
	return Envelope[PaymentNotificationList]{Operation: "payment.notification.list", Status: "ok", Result: result}, err
}

func (service *PaymentDomainService) ReceiveBillEntry(ctx context.Context, tenantID, projectID string, request PaymentBillEntryReceive) (Envelope[PaymentBillEntry], error) {
	if err := validatePaymentScope(tenantID, projectID); err != nil {
		return Envelope[PaymentBillEntry]{}, err
	}
	request = normalizePaymentBillEntryReceive(request)
	if err := validatePaymentBillEntryReceive(request); err != nil {
		return Envelope[PaymentBillEntry]{}, err
	}
	now := service.now().UTC()
	if request.OccurredAt.IsZero() {
		request.OccurredAt = now
	}
	entry := publicPaymentBillEntry(PaymentBillEntry{
		SchemaVersion: PaymentDomainSchemaVersion, TenantID: tenantID, ProjectID: projectID,
		MerchantID: request.MerchantID, Provider: request.Provider, BillEntryID: request.BillEntryID, BillDate: request.BillDate,
		BillKind: request.BillKind, TransactionID: request.TransactionID,
		MerchantOrderID: request.MerchantOrderID, MerchantRefundID: request.MerchantRefundID,
		Amount: request.Amount, Currency: request.Currency, ProviderStatus: request.ProviderStatus,
		SourceSHA256: request.SourceSHA256, OccurredAt: request.OccurredAt.UTC(), ReceivedAt: now,
	})
	entry.MatchStatus, entry.MatchReason = service.reconcileBillEntry(ctx, entry)
	stored, replay, err := service.repository.receiveBillEntry(ctx, entry)
	if err != nil {
		return Envelope[PaymentBillEntry]{}, err
	}
	return Envelope[PaymentBillEntry]{Operation: "payment.bill.receive", Status: "ok", IdempotentReplay: replay, Result: publicPaymentBillEntry(stored)}, nil
}

func (service *PaymentDomainService) GetBillEntry(ctx context.Context, tenantID, projectID, merchantID, provider, billEntryID string) (Envelope[PaymentBillEntry], error) {
	if err := validatePaymentIdentity(tenantID, projectID, merchantID, provider, billEntryID, "bill_entry_id"); err != nil {
		return Envelope[PaymentBillEntry]{}, err
	}
	entry, err := service.repository.getBillEntry(ctx, tenantID, projectID, strings.TrimSpace(merchantID), normalizeChinaPaymentProvider(provider), strings.TrimSpace(billEntryID))
	return Envelope[PaymentBillEntry]{Operation: "payment.bill.get", Status: "ok", Result: publicPaymentBillEntry(entry)}, err
}

func (service *PaymentDomainService) ListBillEntries(ctx context.Context, tenantID, projectID, merchantID, provider, matchStatus string, limit int) (Envelope[PaymentBillEntryList], error) {
	if err := validatePaymentScope(tenantID, projectID); err != nil {
		return Envelope[PaymentBillEntryList]{}, err
	}
	matchStatus = strings.ToLower(strings.TrimSpace(matchStatus))
	if matchStatus != "" && matchStatus != PaymentBillMatchMatched && matchStatus != PaymentBillMatchUnmatched && matchStatus != PaymentBillMatchConflict {
		return Envelope[PaymentBillEntryList]{}, fmt.Errorf("invalid payment bill match status %q", matchStatus)
	}
	merchantID = strings.TrimSpace(merchantID)
	if merchantID == "" {
		return Envelope[PaymentBillEntryList]{}, fmt.Errorf("merchant_id is required")
	}
	provider, err := validateOptionalPaymentProvider(provider)
	if err != nil {
		return Envelope[PaymentBillEntryList]{}, err
	}
	result, err := service.repository.listBillEntries(ctx, tenantID, projectID, merchantID, provider, matchStatus, normalizePaymentListLimit(limit))
	return Envelope[PaymentBillEntryList]{Operation: "payment.bill.list", Status: "ok", Result: result}, err
}

func (service *PaymentDomainService) reconcileBillEntry(ctx context.Context, entry PaymentBillEntry) (string, string) {
	if entry.MerchantRefundID != "" {
		refund, err := service.repository.getRefund(ctx, entry.TenantID, entry.ProjectID, entry.MerchantID, entry.Provider, entry.MerchantRefundID)
		if err != nil {
			return PaymentBillMatchUnmatched, "refund_not_found"
		}
		if refund.Amount != entry.Amount || refund.Currency != entry.Currency {
			return PaymentBillMatchConflict, "refund_amount_or_currency_mismatch"
		}
		return PaymentBillMatchMatched, ""
	}
	if entry.MerchantOrderID != "" {
		order, err := service.repository.getOrder(ctx, entry.TenantID, entry.ProjectID, entry.MerchantID, entry.Provider, entry.MerchantOrderID)
		if err != nil {
			return PaymentBillMatchUnmatched, "order_not_found"
		}
		if order.Amount != entry.Amount || order.Currency != entry.Currency {
			return PaymentBillMatchConflict, "order_amount_or_currency_mismatch"
		}
		return PaymentBillMatchMatched, ""
	}
	return PaymentBillMatchUnmatched, "merchant_reference_missing"
}

type memoryPaymentDomainRepository struct {
	mu            sync.Mutex
	orders        map[string]PaymentOrder
	refunds       map[string]PaymentRefund
	notifications map[string]PaymentNotification
	bills         map[string]PaymentBillEntry
}

func NewMemoryPaymentDomainRepository() paymentDomainRepository {
	return &memoryPaymentDomainRepository{
		orders: map[string]PaymentOrder{}, refunds: map[string]PaymentRefund{},
		notifications: map[string]PaymentNotification{}, bills: map[string]PaymentBillEntry{},
	}
}

func (repository *memoryPaymentDomainRepository) receiveOrder(_ context.Context, order PaymentOrder) (PaymentOrder, bool, error) {
	repository.mu.Lock()
	defer repository.mu.Unlock()
	key := paymentDomainKey(order.TenantID, order.ProjectID, order.MerchantID, order.Provider, order.MerchantOrderID)
	if stored, ok := repository.orders[key]; ok {
		if stored.RequestSHA256 != order.RequestSHA256 {
			return PaymentOrder{}, false, PaymentDomainConflictError{Resource: "order", Provider: order.Provider, ID: order.MerchantOrderID}
		}
		return publicPaymentOrder(stored), true, nil
	}
	repository.orders[key] = order
	return publicPaymentOrder(order), false, nil
}

func (repository *memoryPaymentDomainRepository) getOrder(_ context.Context, tenantID, projectID, merchantID, provider, id string) (PaymentOrder, error) {
	repository.mu.Lock()
	defer repository.mu.Unlock()
	order, ok := repository.orders[paymentDomainKey(tenantID, projectID, merchantID, provider, id)]
	if !ok {
		return PaymentOrder{}, NotFoundError{Resource: "payment order"}
	}
	return publicPaymentOrder(order), nil
}

func (repository *memoryPaymentDomainRepository) listOrders(_ context.Context, tenantID, projectID, merchantID, provider, status string, limit int) (PaymentOrderList, error) {
	repository.mu.Lock()
	defer repository.mu.Unlock()
	orders := make([]PaymentOrder, 0)
	for _, order := range repository.orders {
		if order.TenantID == tenantID && order.ProjectID == projectID && order.MerchantID == merchantID && (provider == "" || order.Provider == provider) && (status == "" || order.Status == status) {
			orders = append(orders, publicPaymentOrder(order))
		}
	}
	sort.Slice(orders, func(i, j int) bool {
		return paymentRecordLess(orders[i].CreatedAt, orders[i].MerchantOrderID, orders[j].CreatedAt, orders[j].MerchantOrderID)
	})
	if len(orders) > limit {
		orders = orders[:limit]
	}
	return PaymentOrderList{SchemaVersion: PaymentDomainSchemaVersion, TenantID: tenantID, ProjectID: projectID, MerchantID: merchantID, Provider: provider, Status: status, Orders: orders, Count: len(orders)}, nil
}

func (repository *memoryPaymentDomainRepository) receiveRefund(_ context.Context, refund PaymentRefund) (PaymentRefund, bool, error) {
	repository.mu.Lock()
	defer repository.mu.Unlock()
	key := paymentDomainKey(refund.TenantID, refund.ProjectID, refund.MerchantID, refund.Provider, refund.MerchantRefundID)
	if stored, ok := repository.refunds[key]; ok {
		if stored.RequestSHA256 != refund.RequestSHA256 {
			return PaymentRefund{}, false, PaymentDomainConflictError{Resource: "refund", Provider: refund.Provider, ID: refund.MerchantRefundID}
		}
		return publicPaymentRefund(stored), true, nil
	}
	repository.refunds[key] = refund
	return publicPaymentRefund(refund), false, nil
}

func (repository *memoryPaymentDomainRepository) getRefund(_ context.Context, tenantID, projectID, merchantID, provider, id string) (PaymentRefund, error) {
	repository.mu.Lock()
	defer repository.mu.Unlock()
	refund, ok := repository.refunds[paymentDomainKey(tenantID, projectID, merchantID, provider, id)]
	if !ok {
		return PaymentRefund{}, NotFoundError{Resource: "payment refund"}
	}
	return publicPaymentRefund(refund), nil
}

func (repository *memoryPaymentDomainRepository) listRefunds(_ context.Context, tenantID, projectID, merchantID, provider, status string, limit int) (PaymentRefundList, error) {
	repository.mu.Lock()
	defer repository.mu.Unlock()
	refunds := make([]PaymentRefund, 0)
	for _, refund := range repository.refunds {
		if refund.TenantID == tenantID && refund.ProjectID == projectID && refund.MerchantID == merchantID && (provider == "" || refund.Provider == provider) && (status == "" || refund.Status == status) {
			refunds = append(refunds, publicPaymentRefund(refund))
		}
	}
	sort.Slice(refunds, func(i, j int) bool {
		return paymentRecordLess(refunds[i].CreatedAt, refunds[i].MerchantRefundID, refunds[j].CreatedAt, refunds[j].MerchantRefundID)
	})
	if len(refunds) > limit {
		refunds = refunds[:limit]
	}
	return PaymentRefundList{SchemaVersion: PaymentDomainSchemaVersion, TenantID: tenantID, ProjectID: projectID, MerchantID: merchantID, Provider: provider, Status: status, Refunds: refunds, Count: len(refunds)}, nil
}

func (repository *memoryPaymentDomainRepository) receiveNotification(_ context.Context, notification PaymentNotification) (PaymentNotification, bool, error) {
	repository.mu.Lock()
	defer repository.mu.Unlock()
	key := paymentDomainKey(notification.TenantID, notification.ProjectID, notification.MerchantID, notification.Provider, notification.ProviderEventID)
	if stored, ok := repository.notifications[key]; ok {
		if stored.PayloadSHA256 != notification.PayloadSHA256 || stored.HeadersSHA256 != notification.HeadersSHA256 ||
			stored.ResourceType != notification.ResourceType || stored.NormalizedStatus != notification.NormalizedStatus {
			return PaymentNotification{}, false, PaymentDomainConflictError{Resource: "notification", Provider: notification.Provider, ID: notification.ProviderEventID}
		}
		return publicPaymentNotification(stored), true, nil
	}
	if err := repository.applyNotificationLocked(&notification); err != nil {
		return PaymentNotification{}, false, err
	}
	repository.notifications[key] = notification
	return publicPaymentNotification(notification), false, nil
}

func (repository *memoryPaymentDomainRepository) applyNotificationLocked(notification *PaymentNotification) error {
	switch notification.ResourceType {
	case "order":
		key := paymentDomainKey(notification.TenantID, notification.ProjectID, notification.MerchantID, notification.Provider, notification.MerchantOrderID)
		order, ok := repository.orders[key]
		if !ok {
			return NotFoundError{Resource: "payment order"}
		}
		updated, replay, err := transitionPaymentOrder(order, notification.NormalizedStatus, notification.ProviderStatus, notification.ProviderObjectID, notification.OccurredAt)
		if err != nil {
			return err
		}
		repository.orders[key] = updated
		notification.Applied = !replay
	case "refund":
		key := paymentDomainKey(notification.TenantID, notification.ProjectID, notification.MerchantID, notification.Provider, notification.MerchantRefundID)
		refund, ok := repository.refunds[key]
		if !ok {
			return NotFoundError{Resource: "payment refund"}
		}
		updated, replay, err := transitionPaymentRefund(refund, notification.NormalizedStatus, notification.ProviderStatus, notification.ProviderObjectID, notification.OccurredAt)
		if err != nil {
			return err
		}
		repository.refunds[key] = updated
		notification.Applied = !replay
	}
	return nil
}

func (repository *memoryPaymentDomainRepository) getNotification(_ context.Context, tenantID, projectID, merchantID, provider, id string) (PaymentNotification, error) {
	repository.mu.Lock()
	defer repository.mu.Unlock()
	event, ok := repository.notifications[paymentDomainKey(tenantID, projectID, merchantID, provider, id)]
	if !ok {
		return PaymentNotification{}, NotFoundError{Resource: "payment notification"}
	}
	return publicPaymentNotification(event), nil
}

func (repository *memoryPaymentDomainRepository) listNotifications(_ context.Context, tenantID, projectID, merchantID, provider string, limit int) (PaymentNotificationList, error) {
	repository.mu.Lock()
	defer repository.mu.Unlock()
	events := make([]PaymentNotification, 0)
	for _, event := range repository.notifications {
		if event.TenantID == tenantID && event.ProjectID == projectID && event.MerchantID == merchantID && (provider == "" || event.Provider == provider) {
			events = append(events, publicPaymentNotification(event))
		}
	}
	sort.Slice(events, func(i, j int) bool {
		return paymentRecordLess(events[i].ReceivedAt, events[i].ProviderEventID, events[j].ReceivedAt, events[j].ProviderEventID)
	})
	if len(events) > limit {
		events = events[:limit]
	}
	return PaymentNotificationList{SchemaVersion: PaymentDomainSchemaVersion, TenantID: tenantID, ProjectID: projectID, MerchantID: merchantID, Provider: provider, Notifications: events, Count: len(events)}, nil
}

func (repository *memoryPaymentDomainRepository) receiveBillEntry(_ context.Context, entry PaymentBillEntry) (PaymentBillEntry, bool, error) {
	repository.mu.Lock()
	defer repository.mu.Unlock()
	key := paymentDomainKey(entry.TenantID, entry.ProjectID, entry.MerchantID, entry.Provider, entry.BillEntryID)
	if stored, ok := repository.bills[key]; ok {
		if stored.SourceSHA256 != entry.SourceSHA256 {
			return PaymentBillEntry{}, false, PaymentDomainConflictError{Resource: "bill entry", Provider: entry.Provider, ID: entry.BillEntryID}
		}
		return publicPaymentBillEntry(stored), true, nil
	}
	repository.bills[key] = entry
	return publicPaymentBillEntry(entry), false, nil
}

func (repository *memoryPaymentDomainRepository) getBillEntry(_ context.Context, tenantID, projectID, merchantID, provider, id string) (PaymentBillEntry, error) {
	repository.mu.Lock()
	defer repository.mu.Unlock()
	entry, ok := repository.bills[paymentDomainKey(tenantID, projectID, merchantID, provider, id)]
	if !ok {
		return PaymentBillEntry{}, NotFoundError{Resource: "payment bill entry"}
	}
	return publicPaymentBillEntry(entry), nil
}

func (repository *memoryPaymentDomainRepository) listBillEntries(_ context.Context, tenantID, projectID, merchantID, provider, matchStatus string, limit int) (PaymentBillEntryList, error) {
	repository.mu.Lock()
	defer repository.mu.Unlock()
	entries := make([]PaymentBillEntry, 0)
	for _, entry := range repository.bills {
		if entry.TenantID == tenantID && entry.ProjectID == projectID && entry.MerchantID == merchantID && (provider == "" || entry.Provider == provider) && (matchStatus == "" || entry.MatchStatus == matchStatus) {
			entries = append(entries, publicPaymentBillEntry(entry))
		}
	}
	sort.Slice(entries, func(i, j int) bool {
		return paymentRecordLess(entries[i].ReceivedAt, entries[i].BillEntryID, entries[j].ReceivedAt, entries[j].BillEntryID)
	})
	if len(entries) > limit {
		entries = entries[:limit]
	}
	return PaymentBillEntryList{SchemaVersion: PaymentDomainSchemaVersion, TenantID: tenantID, ProjectID: projectID, MerchantID: merchantID, Provider: provider, MatchStatus: matchStatus, Entries: entries, Count: len(entries)}, nil
}

func MigratePaymentDomainPostgres(ctx context.Context, db *sql.DB) error {
	if db == nil {
		return fmt.Errorf("postgres db is required")
	}
	if _, err := db.ExecContext(ctx, PaymentDomainSchemaSQL); err != nil {
		return fmt.Errorf("migrate payment domain schema: %w", err)
	}
	return nil
}

func (repository *PostgresRepository) MigratePaymentDomain(ctx context.Context) error {
	if repository == nil || repository.db == nil {
		return fmt.Errorf("postgres db is required")
	}
	return MigratePaymentDomainPostgres(ctx, repository.db)
}

func (repository *PostgresRepository) receiveOrder(ctx context.Context, order PaymentOrder) (PaymentOrder, bool, error) {
	return postgresReceiveJSONRecord(ctx, repository, "ashr_payment_orders", "merchant_order_id", order.TenantID, order.ProjectID, order.MerchantID, order.Provider, order.MerchantOrderID, "request_sha256", order.RequestSHA256, order.CreatedAt, order.UpdatedAt, order, "order", func(payload []byte) (PaymentOrder, error) {
		var value PaymentOrder
		err := json.Unmarshal(payload, &value)
		return publicPaymentOrder(value), err
	})
}

func (repository *PostgresRepository) getOrder(ctx context.Context, tenantID, projectID, merchantID, provider, id string) (PaymentOrder, error) {
	payload, err := postgresGetJSONRecord(ctx, repository, "ashr_payment_orders", "merchant_order_id", tenantID, projectID, merchantID, provider, id, "payment order")
	if err != nil {
		return PaymentOrder{}, err
	}
	var order PaymentOrder
	if err := json.Unmarshal(payload, &order); err != nil {
		return PaymentOrder{}, err
	}
	return publicPaymentOrder(order), nil
}

func (repository *PostgresRepository) listOrders(ctx context.Context, tenantID, projectID, merchantID, provider, status string, limit int) (PaymentOrderList, error) {
	payloads, err := postgresListJSONRecords(ctx, repository, "ashr_payment_orders", "merchant_order_id", tenantID, projectID, merchantID, provider, limit)
	if err != nil {
		return PaymentOrderList{}, err
	}
	orders := make([]PaymentOrder, 0, len(payloads))
	for _, payload := range payloads {
		var order PaymentOrder
		if err := json.Unmarshal(payload, &order); err != nil {
			return PaymentOrderList{}, err
		}
		if status == "" || order.Status == status {
			orders = append(orders, publicPaymentOrder(order))
		}
	}
	return PaymentOrderList{SchemaVersion: PaymentDomainSchemaVersion, TenantID: tenantID, ProjectID: projectID, MerchantID: merchantID, Provider: provider, Status: status, Orders: orders, Count: len(orders)}, nil
}

func (repository *PostgresRepository) receiveRefund(ctx context.Context, refund PaymentRefund) (PaymentRefund, bool, error) {
	return postgresReceiveJSONRecord(ctx, repository, "ashr_payment_refunds", "merchant_refund_id", refund.TenantID, refund.ProjectID, refund.MerchantID, refund.Provider, refund.MerchantRefundID, "request_sha256", refund.RequestSHA256, refund.CreatedAt, refund.UpdatedAt, refund, "refund", func(payload []byte) (PaymentRefund, error) {
		var value PaymentRefund
		err := json.Unmarshal(payload, &value)
		return publicPaymentRefund(value), err
	})
}

func (repository *PostgresRepository) getRefund(ctx context.Context, tenantID, projectID, merchantID, provider, id string) (PaymentRefund, error) {
	payload, err := postgresGetJSONRecord(ctx, repository, "ashr_payment_refunds", "merchant_refund_id", tenantID, projectID, merchantID, provider, id, "payment refund")
	if err != nil {
		return PaymentRefund{}, err
	}
	var refund PaymentRefund
	if err := json.Unmarshal(payload, &refund); err != nil {
		return PaymentRefund{}, err
	}
	return publicPaymentRefund(refund), nil
}

func (repository *PostgresRepository) listRefunds(ctx context.Context, tenantID, projectID, merchantID, provider, status string, limit int) (PaymentRefundList, error) {
	payloads, err := postgresListJSONRecords(ctx, repository, "ashr_payment_refunds", "merchant_refund_id", tenantID, projectID, merchantID, provider, limit)
	if err != nil {
		return PaymentRefundList{}, err
	}
	refunds := make([]PaymentRefund, 0, len(payloads))
	for _, payload := range payloads {
		var refund PaymentRefund
		if err := json.Unmarshal(payload, &refund); err != nil {
			return PaymentRefundList{}, err
		}
		if status == "" || refund.Status == status {
			refunds = append(refunds, publicPaymentRefund(refund))
		}
	}
	return PaymentRefundList{SchemaVersion: PaymentDomainSchemaVersion, TenantID: tenantID, ProjectID: projectID, MerchantID: merchantID, Provider: provider, Status: status, Refunds: refunds, Count: len(refunds)}, nil
}

func (repository *PostgresRepository) receiveNotification(ctx context.Context, notification PaymentNotification) (PaymentNotification, bool, error) {
	if repository == nil || repository.db == nil {
		return PaymentNotification{}, false, fmt.Errorf("postgres db is required")
	}
	tx, err := repository.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return PaymentNotification{}, false, err
	}
	defer rollbackUnlessCommitted(tx)
	placeholderPayload, err := json.Marshal(publicPaymentNotification(notification))
	if err != nil {
		return PaymentNotification{}, false, err
	}
	result, err := tx.ExecContext(ctx, `
INSERT INTO ashr_payment_notifications
(tenant_id, project_id, merchant_id, provider, provider_event_id, payload_sha256, headers_sha256, record_json, received_at)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9)
ON CONFLICT (tenant_id, project_id, merchant_id, provider, provider_event_id) DO NOTHING
`, notification.TenantID, notification.ProjectID, notification.MerchantID, notification.Provider, notification.ProviderEventID, notification.PayloadSHA256, notification.HeadersSHA256, string(placeholderPayload), notification.ReceivedAt)
	if err != nil {
		return PaymentNotification{}, false, err
	}
	inserted, err := result.RowsAffected()
	if err != nil {
		return PaymentNotification{}, false, err
	}
	if inserted == 0 {
		var existingPayload []byte
		var existingHash, existingHeaders string
		err = tx.QueryRowContext(ctx, `
SELECT record_json, payload_sha256, headers_sha256
FROM ashr_payment_notifications
WHERE tenant_id=$1 AND project_id=$2 AND merchant_id=$3 AND provider=$4 AND provider_event_id=$5
FOR UPDATE
`, notification.TenantID, notification.ProjectID, notification.MerchantID, notification.Provider, notification.ProviderEventID).Scan(&existingPayload, &existingHash, &existingHeaders)
		if err != nil {
			return PaymentNotification{}, false, err
		}
		var existing PaymentNotification
		if jsonErr := json.Unmarshal(existingPayload, &existing); jsonErr != nil {
			return PaymentNotification{}, false, jsonErr
		}
		if existingHash != notification.PayloadSHA256 || existingHeaders != notification.HeadersSHA256 ||
			existing.ResourceType != notification.ResourceType || existing.NormalizedStatus != notification.NormalizedStatus {
			return PaymentNotification{}, false, PaymentDomainConflictError{Resource: "notification", Provider: notification.Provider, ID: notification.ProviderEventID}
		}
		if err := tx.Commit(); err != nil {
			return PaymentNotification{}, false, err
		}
		return publicPaymentNotification(existing), true, nil
	}
	if err := postgresApplyNotification(ctx, tx, &notification); err != nil {
		return PaymentNotification{}, false, err
	}
	payload, err := json.Marshal(publicPaymentNotification(notification))
	if err != nil {
		return PaymentNotification{}, false, err
	}
	_, err = tx.ExecContext(ctx, `
UPDATE ashr_payment_notifications
SET record_json=$6::jsonb
WHERE tenant_id=$1 AND project_id=$2 AND merchant_id=$3 AND provider=$4 AND provider_event_id=$5
`, notification.TenantID, notification.ProjectID, notification.MerchantID, notification.Provider, notification.ProviderEventID, string(payload))
	if err != nil {
		return PaymentNotification{}, false, err
	}
	if err := tx.Commit(); err != nil {
		return PaymentNotification{}, false, err
	}
	return publicPaymentNotification(notification), false, nil
}

func postgresApplyNotification(ctx context.Context, tx *sql.Tx, notification *PaymentNotification) error {
	table, idColumn, id, resource := "", "", "", ""
	switch notification.ResourceType {
	case "order":
		table, idColumn, id, resource = "ashr_payment_orders", "merchant_order_id", notification.MerchantOrderID, "payment order"
	case "refund":
		table, idColumn, id, resource = "ashr_payment_refunds", "merchant_refund_id", notification.MerchantRefundID, "payment refund"
	default:
		return fmt.Errorf("unsupported notification resource_type %q", notification.ResourceType)
	}
	query := fmt.Sprintf(`SELECT record_json FROM %s WHERE tenant_id=$1 AND project_id=$2 AND merchant_id=$3 AND provider=$4 AND %s=$5 FOR UPDATE`, table, idColumn)
	var payload []byte
	if err := tx.QueryRowContext(ctx, query, notification.TenantID, notification.ProjectID, notification.MerchantID, notification.Provider, id).Scan(&payload); errors.Is(err, sql.ErrNoRows) {
		return NotFoundError{Resource: resource}
	} else if err != nil {
		return err
	}
	var updated any
	var updatedAt time.Time
	if notification.ResourceType == "order" {
		var order PaymentOrder
		if err := json.Unmarshal(payload, &order); err != nil {
			return err
		}
		next, replay, err := transitionPaymentOrder(order, notification.NormalizedStatus, notification.ProviderStatus, notification.ProviderObjectID, notification.OccurredAt)
		if err != nil {
			return err
		}
		notification.Applied = !replay
		updated, updatedAt = publicPaymentOrder(next), next.UpdatedAt
	} else {
		var refund PaymentRefund
		if err := json.Unmarshal(payload, &refund); err != nil {
			return err
		}
		next, replay, err := transitionPaymentRefund(refund, notification.NormalizedStatus, notification.ProviderStatus, notification.ProviderObjectID, notification.OccurredAt)
		if err != nil {
			return err
		}
		notification.Applied = !replay
		updated, updatedAt = publicPaymentRefund(next), next.UpdatedAt
	}
	updatedPayload, err := json.Marshal(updated)
	if err != nil {
		return err
	}
	update := fmt.Sprintf(`UPDATE %s SET record_json=$6::jsonb, updated_at=$7 WHERE tenant_id=$1 AND project_id=$2 AND merchant_id=$3 AND provider=$4 AND %s=$5`, table, idColumn)
	_, err = tx.ExecContext(ctx, update, notification.TenantID, notification.ProjectID, notification.MerchantID, notification.Provider, id, string(updatedPayload), updatedAt)
	return err
}

func (repository *PostgresRepository) getNotification(ctx context.Context, tenantID, projectID, merchantID, provider, id string) (PaymentNotification, error) {
	payload, err := postgresGetJSONRecord(ctx, repository, "ashr_payment_notifications", "provider_event_id", tenantID, projectID, merchantID, provider, id, "payment notification")
	if err != nil {
		return PaymentNotification{}, err
	}
	var event PaymentNotification
	if err := json.Unmarshal(payload, &event); err != nil {
		return PaymentNotification{}, err
	}
	return publicPaymentNotification(event), nil
}

func (repository *PostgresRepository) listNotifications(ctx context.Context, tenantID, projectID, merchantID, provider string, limit int) (PaymentNotificationList, error) {
	payloads, err := postgresListJSONRecords(ctx, repository, "ashr_payment_notifications", "provider_event_id", tenantID, projectID, merchantID, provider, limit)
	if err != nil {
		return PaymentNotificationList{}, err
	}
	events := make([]PaymentNotification, 0, len(payloads))
	for _, payload := range payloads {
		var event PaymentNotification
		if err := json.Unmarshal(payload, &event); err != nil {
			return PaymentNotificationList{}, err
		}
		events = append(events, publicPaymentNotification(event))
	}
	return PaymentNotificationList{SchemaVersion: PaymentDomainSchemaVersion, TenantID: tenantID, ProjectID: projectID, MerchantID: merchantID, Provider: provider, Notifications: events, Count: len(events)}, nil
}

func (repository *PostgresRepository) receiveBillEntry(ctx context.Context, entry PaymentBillEntry) (PaymentBillEntry, bool, error) {
	return postgresReceiveJSONRecord(ctx, repository, "ashr_payment_bill_entries", "bill_entry_id", entry.TenantID, entry.ProjectID, entry.MerchantID, entry.Provider, entry.BillEntryID, "source_sha256", entry.SourceSHA256, entry.ReceivedAt, entry.ReceivedAt, entry, "bill entry", func(payload []byte) (PaymentBillEntry, error) {
		var value PaymentBillEntry
		err := json.Unmarshal(payload, &value)
		return publicPaymentBillEntry(value), err
	})
}

func (repository *PostgresRepository) getBillEntry(ctx context.Context, tenantID, projectID, merchantID, provider, id string) (PaymentBillEntry, error) {
	payload, err := postgresGetJSONRecord(ctx, repository, "ashr_payment_bill_entries", "bill_entry_id", tenantID, projectID, merchantID, provider, id, "payment bill entry")
	if err != nil {
		return PaymentBillEntry{}, err
	}
	var entry PaymentBillEntry
	if err := json.Unmarshal(payload, &entry); err != nil {
		return PaymentBillEntry{}, err
	}
	return publicPaymentBillEntry(entry), nil
}

func (repository *PostgresRepository) listBillEntries(ctx context.Context, tenantID, projectID, merchantID, provider, matchStatus string, limit int) (PaymentBillEntryList, error) {
	payloads, err := postgresListJSONRecords(ctx, repository, "ashr_payment_bill_entries", "bill_entry_id", tenantID, projectID, merchantID, provider, limit)
	if err != nil {
		return PaymentBillEntryList{}, err
	}
	entries := make([]PaymentBillEntry, 0, len(payloads))
	for _, payload := range payloads {
		var entry PaymentBillEntry
		if err := json.Unmarshal(payload, &entry); err != nil {
			return PaymentBillEntryList{}, err
		}
		if matchStatus == "" || entry.MatchStatus == matchStatus {
			entries = append(entries, publicPaymentBillEntry(entry))
		}
	}
	return PaymentBillEntryList{SchemaVersion: PaymentDomainSchemaVersion, TenantID: tenantID, ProjectID: projectID, MerchantID: merchantID, Provider: provider, MatchStatus: matchStatus, Entries: entries, Count: len(entries)}, nil
}

func postgresReceiveJSONRecord[T any](ctx context.Context, repository *PostgresRepository, table, idColumn, tenantID, projectID, merchantID, provider, id, hashColumn, hash string, createdAt, updatedAt time.Time, value T, resource string, decode func([]byte) (T, error)) (T, bool, error) {
	var zero T
	if repository == nil || repository.db == nil {
		return zero, false, fmt.Errorf("postgres db is required")
	}
	payload, err := json.Marshal(value)
	if err != nil {
		return zero, false, err
	}
	insert := fmt.Sprintf(`
INSERT INTO %s (tenant_id, project_id, merchant_id, provider, %s, %s, record_json, created_at, updated_at)
VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9)
ON CONFLICT (tenant_id, project_id, merchant_id, provider, %s) DO NOTHING
`, table, idColumn, hashColumn, idColumn)
	if table == "ashr_payment_bill_entries" {
		insert = fmt.Sprintf(`
INSERT INTO %s (tenant_id, project_id, merchant_id, provider, %s, %s, record_json, received_at)
VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8)
ON CONFLICT (tenant_id, project_id, merchant_id, provider, %s) DO NOTHING
`, table, idColumn, hashColumn, idColumn)
	}
	args := []any{tenantID, projectID, merchantID, provider, id, hash, string(payload), createdAt, updatedAt}
	if table == "ashr_payment_bill_entries" {
		args = args[:8]
	}
	result, err := repository.db.ExecContext(ctx, insert, args...)
	if err != nil {
		return zero, false, err
	}
	rows, err := result.RowsAffected()
	if err != nil {
		return zero, false, err
	}
	selectQuery := fmt.Sprintf(`SELECT record_json, %s FROM %s WHERE tenant_id=$1 AND project_id=$2 AND merchant_id=$3 AND provider=$4 AND %s=$5`, hashColumn, table, idColumn)
	var storedPayload []byte
	var storedHash string
	if err := repository.db.QueryRowContext(ctx, selectQuery, tenantID, projectID, merchantID, provider, id).Scan(&storedPayload, &storedHash); err != nil {
		return zero, false, err
	}
	if storedHash != hash {
		return zero, false, PaymentDomainConflictError{Resource: resource, Provider: provider, ID: id}
	}
	stored, err := decode(storedPayload)
	return stored, rows == 0, err
}

func postgresGetJSONRecord(ctx context.Context, repository *PostgresRepository, table, idColumn, tenantID, projectID, merchantID, provider, id, resource string) ([]byte, error) {
	if repository == nil || repository.db == nil {
		return nil, fmt.Errorf("postgres db is required")
	}
	query := fmt.Sprintf(`SELECT record_json FROM %s WHERE tenant_id=$1 AND project_id=$2 AND merchant_id=$3 AND provider=$4 AND %s=$5`, table, idColumn)
	var payload []byte
	err := repository.db.QueryRowContext(ctx, query, tenantID, projectID, merchantID, provider, id).Scan(&payload)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, NotFoundError{Resource: resource}
	}
	return payload, err
}

func postgresListJSONRecords(ctx context.Context, repository *PostgresRepository, table, idColumn, tenantID, projectID, merchantID, provider string, limit int) ([][]byte, error) {
	if repository == nil || repository.db == nil {
		return nil, fmt.Errorf("postgres db is required")
	}
	timeColumn := "created_at"
	if table == "ashr_payment_notifications" || table == "ashr_payment_bill_entries" {
		timeColumn = "received_at"
	}
	query := fmt.Sprintf(`
SELECT record_json FROM %s
WHERE tenant_id=$1 AND project_id=$2 AND merchant_id=$3 AND ($4='' OR provider=$4)
ORDER BY %s ASC, provider ASC, %s ASC
LIMIT $5
`, table, timeColumn, idColumn)
	rows, err := repository.db.QueryContext(ctx, query, tenantID, projectID, merchantID, provider, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	payloads := make([][]byte, 0)
	for rows.Next() {
		var payload []byte
		if err := rows.Scan(&payload); err != nil {
			return nil, err
		}
		payloads = append(payloads, payload)
	}
	return payloads, rows.Err()
}

func transitionPaymentOrder(order PaymentOrder, targetStatus, providerStatus, providerOrderID string, at time.Time) (PaymentOrder, bool, error) {
	if order.Status == targetStatus {
		if order.ProviderStatus != providerStatus || (providerOrderID != "" && order.ProviderOrderID != providerOrderID) {
			return PaymentOrder{}, false, PaymentDomainConflictError{Resource: "order transition", Provider: order.Provider, ID: order.MerchantOrderID}
		}
		return publicPaymentOrder(order), true, nil
	}
	if !allowedPaymentOrderTransition(order.Status, targetStatus) {
		return PaymentOrder{}, false, PaymentReconciliationTransitionError{Provider: order.Provider, ProviderEventID: order.MerchantOrderID, From: order.Status, To: targetStatus}
	}
	at = at.UTC()
	order.Status, order.ProviderStatus, order.UpdatedAt = targetStatus, providerStatus, at
	if providerOrderID != "" {
		order.ProviderOrderID = providerOrderID
	}
	switch targetStatus {
	case PaymentOrderStatusSucceeded:
		order.SucceededAt = paymentTimePointer(at)
	case PaymentOrderStatusClosed:
		order.ClosedAt = paymentTimePointer(at)
	case PaymentOrderStatusFailed:
		order.FailedAt = paymentTimePointer(at)
	}
	return publicPaymentOrder(order), false, nil
}

func transitionPaymentRefund(refund PaymentRefund, targetStatus, providerStatus, providerRefundID string, at time.Time) (PaymentRefund, bool, error) {
	if refund.Status == targetStatus {
		if refund.ProviderStatus != providerStatus || (providerRefundID != "" && refund.ProviderRefundID != providerRefundID) {
			return PaymentRefund{}, false, PaymentDomainConflictError{Resource: "refund transition", Provider: refund.Provider, ID: refund.MerchantRefundID}
		}
		return publicPaymentRefund(refund), true, nil
	}
	if !allowedPaymentRefundTransition(refund.Status, targetStatus) {
		return PaymentRefund{}, false, PaymentReconciliationTransitionError{Provider: refund.Provider, ProviderEventID: refund.MerchantRefundID, From: refund.Status, To: targetStatus}
	}
	at = at.UTC()
	refund.Status, refund.ProviderStatus, refund.UpdatedAt = targetStatus, providerStatus, at
	if providerRefundID != "" {
		refund.ProviderRefundID = providerRefundID
	}
	switch targetStatus {
	case PaymentRefundStatusSucceeded:
		refund.SucceededAt = paymentTimePointer(at)
	case PaymentRefundStatusClosed:
		refund.ClosedAt = paymentTimePointer(at)
	case PaymentRefundStatusFailed:
		refund.FailedAt = paymentTimePointer(at)
	}
	return publicPaymentRefund(refund), false, nil
}

func paymentProviderProfiles() map[string]PaymentProviderCapabilities {
	commonCapabilities := map[string]bool{
		"orders": true, "refunds": true, "notifications": true, "bill_reconciliation": true,
		"real_provider_calls": false, "raw_payload_storage": false, "pan_cvc_otp_accepted": false,
	}
	return map[string]PaymentProviderCapabilities{
		PaymentProviderWeChatPay: {
			SchemaVersion: PaymentDomainSchemaVersion, Provider: PaymentProviderWeChatPay, DisplayName: "WeChat Pay",
			OrderStatuses:         []string{PaymentOrderStatusCreated, PaymentOrderStatusPending, PaymentOrderStatusSucceeded, PaymentOrderStatusClosed, PaymentOrderStatusFailed},
			RefundStatuses:        []string{PaymentRefundStatusCreated, PaymentRefundStatusProcessing, PaymentRefundStatusSucceeded, PaymentRefundStatusClosed, PaymentRefundStatusFailed},
			NotificationResources: []string{"order", "refund"}, Channels: []string{"native", "jsapi", "app", "h5", "mini_program"},
			BillKinds: []string{"transaction", "fund_flow", "refund"}, Capabilities: cloneBoolMap(commonCapabilities),
			ProviderStatusMap: map[string]string{"NOTPAY": PaymentOrderStatusPending, "USERPAYING": PaymentOrderStatusPending, "SUCCESS": PaymentOrderStatusSucceeded, "CLOSED": PaymentOrderStatusClosed, "REVOKED": PaymentOrderStatusClosed, "PAYERROR": PaymentOrderStatusFailed},
			RefundStatusMap:   map[string]string{"PROCESSING": PaymentRefundStatusProcessing, "SUCCESS": PaymentRefundStatusSucceeded, "CLOSED": PaymentRefundStatusClosed, "ABNORMAL": PaymentRefundStatusFailed},
		},
		PaymentProviderAlipay: {
			SchemaVersion: PaymentDomainSchemaVersion, Provider: PaymentProviderAlipay, DisplayName: "Alipay",
			OrderStatuses:         []string{PaymentOrderStatusCreated, PaymentOrderStatusPending, PaymentOrderStatusSucceeded, PaymentOrderStatusClosed, PaymentOrderStatusFailed},
			RefundStatuses:        []string{PaymentRefundStatusCreated, PaymentRefundStatusProcessing, PaymentRefundStatusSucceeded, PaymentRefundStatusClosed, PaymentRefundStatusFailed},
			NotificationResources: []string{"order", "refund"}, Channels: []string{"page", "wap", "app", "face_to_face", "mini_program"},
			BillKinds: []string{"trade", "signcustomer", "refund"}, Capabilities: cloneBoolMap(commonCapabilities),
			ProviderStatusMap: map[string]string{"WAIT_BUYER_PAY": PaymentOrderStatusPending, "TRADE_SUCCESS": PaymentOrderStatusSucceeded, "TRADE_FINISHED": PaymentOrderStatusSucceeded, "TRADE_CLOSED": PaymentOrderStatusClosed, "TRADE_FAILED": PaymentOrderStatusFailed},
			RefundStatusMap:   map[string]string{"REFUND_PROCESSING": PaymentRefundStatusProcessing, "REFUND_SUCCESS": PaymentRefundStatusSucceeded, "REFUND_CLOSED": PaymentRefundStatusClosed, "REFUND_FAILED": PaymentRefundStatusFailed},
		},
		PaymentProviderStripe: {
			SchemaVersion: PaymentDomainSchemaVersion, Provider: PaymentProviderStripe, DisplayName: "Stripe",
			OrderStatuses:         []string{PaymentOrderStatusCreated, PaymentOrderStatusPending, PaymentOrderStatusSucceeded, PaymentOrderStatusClosed, PaymentOrderStatusFailed},
			RefundStatuses:        []string{PaymentRefundStatusCreated, PaymentRefundStatusProcessing, PaymentRefundStatusSucceeded, PaymentRefundStatusClosed, PaymentRefundStatusFailed},
			NotificationResources: []string{"order", "refund"}, Channels: []string{"checkout", "payment_intent"},
			BillKinds: []string{"balance_transaction", "payout", "refund"}, Capabilities: cloneBoolMap(commonCapabilities),
			ProviderStatusMap: map[string]string{"requires_payment_method": PaymentOrderStatusPending, "requires_action": PaymentOrderStatusPending, "processing": PaymentOrderStatusPending, "succeeded": PaymentOrderStatusSucceeded, "canceled": PaymentOrderStatusClosed, "failed": PaymentOrderStatusFailed},
			RefundStatusMap:   map[string]string{"pending": PaymentRefundStatusProcessing, "requires_action": PaymentRefundStatusProcessing, "succeeded": PaymentRefundStatusSucceeded, "canceled": PaymentRefundStatusClosed, "failed": PaymentRefundStatusFailed},
		},
		PaymentProviderDomesticBankCard: {
			SchemaVersion: PaymentDomainSchemaVersion, Provider: PaymentProviderDomesticBankCard, DisplayName: "Domestic Bank Card",
			OrderStatuses:         []string{PaymentOrderStatusCreated, PaymentOrderStatusPending, PaymentOrderStatusSucceeded, PaymentOrderStatusClosed, PaymentOrderStatusFailed},
			RefundStatuses:        []string{PaymentRefundStatusCreated, PaymentRefundStatusProcessing, PaymentRefundStatusSucceeded, PaymentRefundStatusClosed, PaymentRefundStatusFailed},
			NotificationResources: []string{"order", "refund"}, Channels: []string{"acquirer_hosted", "acquirer_token"},
			BillKinds: []string{"transaction", "settlement", "refund", "chargeback"}, Capabilities: mergeBoolMaps(commonCapabilities, map[string]bool{
				"acquirer_hosted": true, "acquirer_token_reference": true,
			}),
			ProviderStatusMap: map[string]string{"PENDING": PaymentOrderStatusPending, "PROCESSING": PaymentOrderStatusPending, "SUCCESS": PaymentOrderStatusSucceeded, "SETTLED": PaymentOrderStatusSucceeded, "CLOSED": PaymentOrderStatusClosed, "FAILED": PaymentOrderStatusFailed},
			RefundStatusMap:   map[string]string{"PENDING": PaymentRefundStatusProcessing, "PROCESSING": PaymentRefundStatusProcessing, "SUCCESS": PaymentRefundStatusSucceeded, "SETTLED": PaymentRefundStatusSucceeded, "CLOSED": PaymentRefundStatusClosed, "FAILED": PaymentRefundStatusFailed},
		},
	}
}

func normalizePaymentOrderReceive(request PaymentOrderReceive) PaymentOrderReceive {
	request.Provider = normalizeChinaPaymentProvider(request.Provider)
	request.MerchantID = strings.TrimSpace(request.MerchantID)
	request.MerchantOrderID = strings.TrimSpace(request.MerchantOrderID)
	request.Currency = strings.ToUpper(strings.TrimSpace(request.Currency))
	request.Description = strings.TrimSpace(request.Description)
	request.Channel = strings.ToLower(strings.TrimSpace(request.Channel))
	request.CustomerRef = strings.TrimSpace(request.CustomerRef)
	request.AcquirerReference = strings.TrimSpace(request.AcquirerReference)
	request.PaymentMethodTokenReference = strings.TrimSpace(request.PaymentMethodTokenReference)
	request.Metadata = sanitizedBillingMetadata(request.Metadata)
	return request
}

func validatePaymentOrderReceive(request PaymentOrderReceive) error {
	if err := rejectPaymentCardSecrets(request.Metadata); err != nil {
		return err
	}
	profile, err := PaymentProviderCapability(request.Provider)
	if err != nil {
		return err
	}
	if request.MerchantID == "" || request.MerchantOrderID == "" {
		return fmt.Errorf("merchant_id and merchant_order_id are required")
	}
	if request.Amount <= 0 {
		return fmt.Errorf("amount must be positive minor units")
	}
	if !validPaymentCurrency(request.Currency) {
		return fmt.Errorf("currency must be a three-letter uppercase code")
	}
	if isChinaDomesticPaymentProvider(request.Provider) && request.Currency != "CNY" {
		return fmt.Errorf("%s orders require CNY amounts in fen", request.Provider)
	}
	if request.Channel != "" && !containsString(profile.Channels, request.Channel) {
		return fmt.Errorf("unsupported %s channel %q", request.Provider, request.Channel)
	}
	if request.Provider == PaymentProviderDomesticBankCard {
		if request.Channel == "" || (request.AcquirerReference == "" && request.PaymentMethodTokenReference == "") {
			return fmt.Errorf("domestic_bank_card requires an acquirer-hosted channel and token/reference")
		}
		if err := validateDomesticBankCardReferences(request.AcquirerReference, request.PaymentMethodTokenReference, request.CustomerRef, request.Metadata); err != nil {
			return err
		}
	}
	return nil
}

func normalizePaymentRefundReceive(request PaymentRefundReceive) PaymentRefundReceive {
	request.Provider = normalizeChinaPaymentProvider(request.Provider)
	request.MerchantID = strings.TrimSpace(request.MerchantID)
	request.MerchantRefundID = strings.TrimSpace(request.MerchantRefundID)
	request.MerchantOrderID = strings.TrimSpace(request.MerchantOrderID)
	request.Currency = strings.ToUpper(strings.TrimSpace(request.Currency))
	request.Reason = strings.TrimSpace(request.Reason)
	request.Metadata = sanitizedBillingMetadata(request.Metadata)
	return request
}

func validatePaymentRefundReceive(request PaymentRefundReceive) error {
	if _, err := PaymentProviderCapability(request.Provider); err != nil {
		return err
	}
	if request.MerchantID == "" || request.MerchantRefundID == "" || request.MerchantOrderID == "" {
		return fmt.Errorf("merchant_id, merchant_refund_id, and merchant_order_id are required")
	}
	if request.Amount <= 0 {
		return fmt.Errorf("amount must be positive minor units")
	}
	if !validPaymentCurrency(request.Currency) {
		return fmt.Errorf("currency must be a three-letter uppercase code")
	}
	if isChinaDomesticPaymentProvider(request.Provider) && request.Currency != "CNY" {
		return fmt.Errorf("%s refunds require CNY amounts in fen", request.Provider)
	}
	if err := rejectPaymentCardSecrets(request.Metadata); err != nil {
		return err
	}
	return nil
}

func normalizePaymentNotificationReceive(request PaymentNotificationReceive) PaymentNotificationReceive {
	request.Provider = normalizeChinaPaymentProvider(request.Provider)
	request.MerchantID = strings.TrimSpace(request.MerchantID)
	request.ProviderEventID = strings.TrimSpace(request.ProviderEventID)
	request.EventType = strings.TrimSpace(request.EventType)
	request.ResourceType = strings.ToLower(strings.TrimSpace(request.ResourceType))
	request.MerchantOrderID = strings.TrimSpace(request.MerchantOrderID)
	request.MerchantRefundID = strings.TrimSpace(request.MerchantRefundID)
	request.ProviderObjectID = strings.TrimSpace(request.ProviderObjectID)
	request.ProviderStatus = strings.TrimSpace(request.ProviderStatus)
	request.PayloadSHA256 = strings.ToLower(strings.TrimSpace(request.PayloadSHA256))
	request.HeadersSHA256 = strings.ToLower(strings.TrimSpace(request.HeadersSHA256))
	return request
}

func validateAndNormalizePaymentNotification(request PaymentNotificationReceive) (string, error) {
	profile, err := PaymentProviderCapability(request.Provider)
	if err != nil {
		return "", err
	}
	if request.MerchantID == "" || request.ProviderEventID == "" || request.EventType == "" || request.ProviderStatus == "" {
		return "", fmt.Errorf("merchant_id, provider_event_id, event_type, and provider_status are required")
	}
	if !paymentSHA256Pattern.MatchString(request.PayloadSHA256) || (request.HeadersSHA256 != "" && !paymentSHA256Pattern.MatchString(request.HeadersSHA256)) {
		return "", fmt.Errorf("notification hashes must be lowercase SHA-256 digests")
	}
	switch request.ResourceType {
	case "order":
		if request.MerchantOrderID == "" {
			return "", fmt.Errorf("merchant_order_id is required for order notifications")
		}
		status, ok := providerStatusLookup(profile.ProviderStatusMap, request.ProviderStatus)
		if !ok {
			return "", fmt.Errorf("unsupported %s order status %q", request.Provider, request.ProviderStatus)
		}
		return status, nil
	case "refund":
		if request.MerchantRefundID == "" {
			return "", fmt.Errorf("merchant_refund_id is required for refund notifications")
		}
		status, ok := providerStatusLookup(profile.RefundStatusMap, request.ProviderStatus)
		if !ok {
			return "", fmt.Errorf("unsupported %s refund status %q", request.Provider, request.ProviderStatus)
		}
		return status, nil
	default:
		return "", fmt.Errorf("resource_type must be order or refund")
	}
}

func normalizePaymentBillEntryReceive(request PaymentBillEntryReceive) PaymentBillEntryReceive {
	request.Provider = normalizeChinaPaymentProvider(request.Provider)
	request.MerchantID = strings.TrimSpace(request.MerchantID)
	request.BillEntryID = strings.TrimSpace(request.BillEntryID)
	request.BillDate = strings.TrimSpace(request.BillDate)
	request.BillKind = strings.ToLower(strings.TrimSpace(request.BillKind))
	request.TransactionID = strings.TrimSpace(request.TransactionID)
	request.MerchantOrderID = strings.TrimSpace(request.MerchantOrderID)
	request.MerchantRefundID = strings.TrimSpace(request.MerchantRefundID)
	request.Currency = strings.ToUpper(strings.TrimSpace(request.Currency))
	request.ProviderStatus = strings.TrimSpace(request.ProviderStatus)
	request.SourceSHA256 = strings.ToLower(strings.TrimSpace(request.SourceSHA256))
	return request
}

func validatePaymentBillEntryReceive(request PaymentBillEntryReceive) error {
	profile, err := PaymentProviderCapability(request.Provider)
	if err != nil {
		return err
	}
	if request.MerchantID == "" || request.BillEntryID == "" || request.BillDate == "" || request.BillKind == "" || request.ProviderStatus == "" {
		return fmt.Errorf("merchant_id, bill_entry_id, bill_date, bill_kind, and provider_status are required")
	}
	if _, err := time.Parse("2006-01-02", request.BillDate); err != nil {
		return fmt.Errorf("bill_date must use YYYY-MM-DD")
	}
	if !containsString(profile.BillKinds, request.BillKind) {
		return fmt.Errorf("unsupported %s bill_kind %q", request.Provider, request.BillKind)
	}
	if request.Amount <= 0 || !validPaymentCurrency(request.Currency) {
		return fmt.Errorf("bill amount and currency are invalid")
	}
	if isChinaDomesticPaymentProvider(request.Provider) && request.Currency != "CNY" {
		return fmt.Errorf("%s bills require CNY amounts in fen", request.Provider)
	}
	if !paymentSHA256Pattern.MatchString(request.SourceSHA256) {
		return fmt.Errorf("source_sha256 must be a lowercase SHA-256 digest")
	}
	return nil
}

func normalizeChinaPaymentProvider(provider string) string {
	switch strings.ToLower(strings.TrimSpace(provider)) {
	case "wechat", "wechatpay", "weixin", "wxpay", PaymentProviderWeChatPay:
		return PaymentProviderWeChatPay
	case "ali_pay", PaymentProviderAlipay:
		return PaymentProviderAlipay
	case PaymentProviderStripe:
		return PaymentProviderStripe
	case "bank_card", "domestic_card", "unionpay_card", PaymentProviderDomesticBankCard:
		return PaymentProviderDomesticBankCard
	default:
		return strings.ToLower(strings.TrimSpace(provider))
	}
}

func isChinaDomesticPaymentProvider(provider string) bool {
	switch normalizeChinaPaymentProvider(provider) {
	case PaymentProviderWeChatPay, PaymentProviderAlipay, PaymentProviderDomesticBankCard:
		return true
	default:
		return false
	}
}

func validateOptionalPaymentProvider(provider string) (string, error) {
	if strings.TrimSpace(provider) == "" {
		return "", nil
	}
	normalized := normalizeChinaPaymentProvider(provider)
	if _, err := PaymentProviderCapability(normalized); err != nil {
		return "", err
	}
	return normalized, nil
}

func validatePaymentIdentity(tenantID, projectID, merchantID, provider, id, idName string) error {
	if err := validatePaymentScope(tenantID, projectID); err != nil {
		return err
	}
	if _, err := PaymentProviderCapability(provider); err != nil {
		return err
	}
	if strings.TrimSpace(merchantID) == "" {
		return fmt.Errorf("merchant_id is required")
	}
	if strings.TrimSpace(id) == "" {
		return fmt.Errorf("%s is required", idName)
	}
	return nil
}

func allowedPaymentOrderTransition(from, to string) bool {
	if from == PaymentOrderStatusCreated {
		return to == PaymentOrderStatusPending || to == PaymentOrderStatusSucceeded || to == PaymentOrderStatusClosed || to == PaymentOrderStatusFailed
	}
	if from == PaymentOrderStatusPending {
		return to == PaymentOrderStatusSucceeded || to == PaymentOrderStatusClosed || to == PaymentOrderStatusFailed
	}
	return false
}

func allowedPaymentRefundTransition(from, to string) bool {
	if from == PaymentRefundStatusCreated {
		return to == PaymentRefundStatusProcessing || to == PaymentRefundStatusSucceeded || to == PaymentRefundStatusClosed || to == PaymentRefundStatusFailed
	}
	if from == PaymentRefundStatusProcessing {
		return to == PaymentRefundStatusSucceeded || to == PaymentRefundStatusClosed || to == PaymentRefundStatusFailed
	}
	return false
}

func validPaymentOrderStatus(status string) bool {
	return containsString([]string{PaymentOrderStatusCreated, PaymentOrderStatusPending, PaymentOrderStatusSucceeded, PaymentOrderStatusClosed, PaymentOrderStatusFailed}, status)
}

func validPaymentRefundStatus(status string) bool {
	return containsString([]string{PaymentRefundStatusCreated, PaymentRefundStatusProcessing, PaymentRefundStatusSucceeded, PaymentRefundStatusClosed, PaymentRefundStatusFailed}, status)
}

func validPaymentCurrency(currency string) bool {
	if len(currency) != 3 {
		return false
	}
	for _, char := range currency {
		if char < 'A' || char > 'Z' {
			return false
		}
	}
	return true
}

func providerStatusLookup(statuses map[string]string, status string) (string, bool) {
	if value, ok := statuses[status]; ok {
		return value, true
	}
	if value, ok := statuses[strings.ToUpper(status)]; ok {
		return value, true
	}
	value, ok := statuses[strings.ToLower(status)]
	return value, ok
}

func publicPaymentOrder(order PaymentOrder) PaymentOrder {
	order.SchemaVersion, order.RawPayloadIncluded, order.SecretValuePresent = PaymentDomainSchemaVersion, false, false
	order.Metadata = sanitizedBillingMetadata(order.Metadata)
	return order
}

func publicPaymentRefund(refund PaymentRefund) PaymentRefund {
	refund.SchemaVersion, refund.RawPayloadIncluded, refund.SecretValuePresent = PaymentDomainSchemaVersion, false, false
	refund.Metadata = sanitizedBillingMetadata(refund.Metadata)
	return refund
}

func publicPaymentNotification(event PaymentNotification) PaymentNotification {
	event.SchemaVersion, event.RawPayloadIncluded, event.RawHeadersIncluded, event.SecretValuePresent = PaymentDomainSchemaVersion, false, false, false
	return event
}

func publicPaymentBillEntry(entry PaymentBillEntry) PaymentBillEntry {
	entry.SchemaVersion, entry.RawPayloadIncluded, entry.SecretValuePresent = PaymentDomainSchemaVersion, false, false
	return entry
}

func paymentDomainKey(tenantID, projectID, merchantID, provider, id string) string {
	return tenantID + "\x00" + projectID + "\x00" + merchantID + "\x00" + provider + "\x00" + id
}

func paymentRecordLess(leftTime time.Time, leftID string, rightTime time.Time, rightID string) bool {
	if !leftTime.Equal(rightTime) {
		return leftTime.Before(rightTime)
	}
	return leftID < rightID
}

func containsString(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func cloneBoolMap(source map[string]bool) map[string]bool {
	result := make(map[string]bool, len(source))
	for key, value := range source {
		result[key] = value
	}
	return result
}

func mergeBoolMaps(base, overlay map[string]bool) map[string]bool {
	result := cloneBoolMap(base)
	for key, value := range overlay {
		result[key] = value
	}
	return result
}

var forbiddenPaymentCardFieldNames = map[string]struct{}{
	"pan": {}, "cardnumber": {}, "primaryaccountnumber": {},
	"cvc": {}, "cvv": {}, "cvv2": {}, "securitycode": {},
	"otp": {}, "onetimepassword": {}, "smscode": {},
	"pin": {}, "cardpin": {}, "expiry": {}, "expirydate": {}, "expirationdate": {},
}

func validateDomesticBankCardReferences(acquirerReference, tokenReference, customerReference string, metadata JSONMap) error {
	if err := rejectPaymentCardSecrets(metadata); err != nil {
		return err
	}
	for name, value := range map[string]string{
		"acquirer_reference":             acquirerReference,
		"payment_method_token_reference": tokenReference,
		"customer_ref":                   customerReference,
	} {
		if value == "" {
			continue
		}
		if len(value) > 256 {
			return fmt.Errorf("%s must be at most 256 characters", name)
		}
		if containsPaymentCardNumber(value) {
			return fmt.Errorf("%s must be an opaque hosted/token reference, not card data", name)
		}
		for _, char := range value {
			if unicode.IsControl(char) {
				return fmt.Errorf("%s contains invalid control characters", name)
			}
		}
	}
	return nil
}

func rejectPaymentCardSecrets(value any) error {
	return walkPaymentCardSecrets(reflect.ValueOf(value), "")
}

func walkPaymentCardSecrets(value reflect.Value, path string) error {
	if !value.IsValid() {
		return nil
	}
	if value.Kind() == reflect.Interface || value.Kind() == reflect.Pointer {
		if value.IsNil() {
			return nil
		}
		return walkPaymentCardSecrets(value.Elem(), path)
	}
	switch value.Kind() {
	case reflect.Map:
		iter := value.MapRange()
		for iter.Next() {
			key := fmt.Sprint(iter.Key().Interface())
			normalized := normalizeSensitivePaymentFieldName(key)
			if _, forbidden := forbiddenPaymentCardFieldNames[normalized]; forbidden {
				return fmt.Errorf("payment card secret field %q is forbidden", paymentFieldPath(path, key))
			}
			if err := walkPaymentCardSecrets(iter.Value(), paymentFieldPath(path, key)); err != nil {
				return err
			}
		}
	case reflect.Slice, reflect.Array:
		for index := 0; index < value.Len(); index++ {
			if err := walkPaymentCardSecrets(value.Index(index), path+"["+strconv.Itoa(index)+"]"); err != nil {
				return err
			}
		}
	case reflect.String:
		if containsPaymentCardNumber(value.String()) {
			return fmt.Errorf("payment card number is forbidden in %q", path)
		}
	}
	return nil
}

func normalizeSensitivePaymentFieldName(value string) string {
	var builder strings.Builder
	for _, char := range strings.ToLower(value) {
		if unicode.IsLetter(char) || unicode.IsDigit(char) {
			builder.WriteRune(char)
		}
	}
	return builder.String()
}

func paymentFieldPath(parent, child string) string {
	if parent == "" {
		return child
	}
	return parent + "." + child
}

func containsPaymentCardNumber(value string) bool {
	var digits strings.Builder
	flush := func() bool {
		candidate := digits.String()
		digits.Reset()
		return len(candidate) >= 13 && len(candidate) <= 19 && luhnValid(candidate)
	}
	for _, char := range value {
		switch {
		case char >= '0' && char <= '9':
			digits.WriteRune(char)
		case char == ' ' || char == '-':
			continue
		default:
			if flush() {
				return true
			}
		}
	}
	return flush()
}

func luhnValid(digits string) bool {
	sum := 0
	double := false
	for index := len(digits) - 1; index >= 0; index-- {
		value := int(digits[index] - '0')
		if double {
			value *= 2
			if value > 9 {
				value -= 9
			}
		}
		sum += value
		double = !double
	}
	return sum > 0 && sum%10 == 0
}

func cloneStringMap(source map[string]string) map[string]string {
	result := make(map[string]string, len(source))
	for key, value := range source {
		result[key] = value
	}
	return result
}

func clonePaymentProviderCapabilities(value PaymentProviderCapabilities) PaymentProviderCapabilities {
	value.OrderStatuses = append([]string(nil), value.OrderStatuses...)
	value.RefundStatuses = append([]string(nil), value.RefundStatuses...)
	value.NotificationResources = append([]string(nil), value.NotificationResources...)
	value.Channels = append([]string(nil), value.Channels...)
	value.BillKinds = append([]string(nil), value.BillKinds...)
	value.Capabilities = cloneBoolMap(value.Capabilities)
	value.ProviderStatusMap = cloneStringMap(value.ProviderStatusMap)
	value.RefundStatusMap = cloneStringMap(value.RefundStatusMap)
	return value
}

var _ paymentDomainRepository = (*memoryPaymentDomainRepository)(nil)
var _ paymentDomainRepository = (*PostgresRepository)(nil)
