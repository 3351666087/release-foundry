package ashrclone

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"
)

func newPaymentDomainTestService(t *testing.T) *PaymentDomainService {
	t.Helper()
	service, err := NewPaymentDomainService(NewMemoryPaymentDomainRepository())
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 7, 10, 10, 0, 0, 0, time.UTC)
	service.now = func() time.Time {
		now = now.Add(time.Second)
		return now
	}
	return service
}

func testPaymentOrder(provider, merchantID, orderID string) PaymentOrderReceive {
	return PaymentOrderReceive{
		Provider: provider, MerchantID: merchantID, MerchantOrderID: orderID,
		Amount: 1234, Currency: "CNY", Channel: "native",
	}
}

func receiveVerifiedPaymentNotificationForTest(t *testing.T, service *PaymentDomainService, ctx context.Context, tenantID, projectID string, request PaymentNotificationReceive) (Envelope[PaymentNotification], error) {
	t.Helper()
	verifiedAt := time.Date(2026, 7, 10, 10, 0, 0, 0, time.UTC)
	if request.OccurredAt.IsZero() {
		request.OccurredAt = verifiedAt
	}
	sealed, err := service.issueVerifiedPaymentNotification(request, paymentVerificationEvidence{
		VerifierID: "test.provider.verifier", VerifierVersion: "1.0.0",
		SignatureSHA256: testPaymentFailureHash, CertificateKeyRef: "test-key-ref",
		VerifiedAt: verifiedAt, ProviderTimestamp: "1783658400", ProviderNonce: "test-nonce",
	})
	if err != nil {
		t.Fatalf("issue verified notification: %v", err)
	}
	return service.receiveVerifiedNotification(ctx, tenantID, projectID, sealed)
}

func TestPaymentDomainCapabilitiesRetainStripeAndFirstClassChinaRails(t *testing.T) {
	list := PaymentProviderCapabilitiesList()
	if list.Count != 4 {
		t.Fatalf("provider count = %d, want 4", list.Count)
	}
	providers := map[string]PaymentProviderCapabilities{}
	for _, profile := range list.Providers {
		providers[profile.Provider] = profile
		if profile.Capabilities["real_provider_calls"] || profile.Capabilities["raw_payload_storage"] || profile.Capabilities["pan_cvc_otp_accepted"] {
			t.Fatalf("unsafe provider capabilities: %#v", profile)
		}
	}
	for _, provider := range []string{PaymentProviderStripe, PaymentProviderWeChatPay, PaymentProviderAlipay, PaymentProviderDomesticBankCard} {
		if _, ok := providers[provider]; !ok {
			t.Fatalf("missing provider %q", provider)
		}
	}
	stripe := providers[PaymentProviderStripe]
	if stripe.ProviderStatusMap["succeeded"] != PaymentOrderStatusSucceeded || stripe.RefundStatusMap["succeeded"] != PaymentRefundStatusSucceeded {
		t.Fatalf("Stripe status compatibility lost: %#v", stripe)
	}
	card := providers[PaymentProviderDomesticBankCard]
	if !card.Capabilities["acquirer_hosted"] || !card.Capabilities["acquirer_token_reference"] {
		t.Fatalf("domestic card hosted/token capabilities missing: %#v", card)
	}
}

func TestPaymentDomainChinaRailsRequireCNYFenAndStripeRemainsCurrencyCompatible(t *testing.T) {
	service := newPaymentDomainTestService(t)
	for _, provider := range []string{PaymentProviderWeChatPay, PaymentProviderAlipay, PaymentProviderDomesticBankCard} {
		request := testPaymentOrder(provider, "merchant_a", "order_"+provider)
		request.Currency = "USD"
		if provider == PaymentProviderAlipay {
			request.Channel = "app"
		}
		if provider == PaymentProviderDomesticBankCard {
			request.Channel = "acquirer_hosted"
			request.AcquirerReference = "acq_ref_123"
		}
		if _, err := service.ReceiveOrder(context.Background(), "tenant", "project", request); err == nil || !strings.Contains(err.Error(), "CNY") {
			t.Fatalf("%s accepted non-CNY order: %v", provider, err)
		}
	}
	stripe := testPaymentOrder(PaymentProviderStripe, "merchant_a", "stripe_usd")
	stripe.Currency, stripe.Channel = "USD", "payment_intent"
	if _, err := service.ReceiveOrder(context.Background(), "tenant", "project", stripe); err != nil {
		t.Fatalf("Stripe USD compatibility failed: %v", err)
	}
}

func TestPaymentDomainDomesticCardRequiresHostedTokenReferencesAndRejectsSecrets(t *testing.T) {
	service := newPaymentDomainTestService(t)
	valid := testPaymentOrder(PaymentProviderDomesticBankCard, "merchant_card", "card_order")
	valid.Channel = "acquirer_token"
	valid.PaymentMethodTokenReference = "tok_acquirer_opaque"
	if _, err := service.ReceiveOrder(context.Background(), "tenant", "project", valid); err != nil {
		t.Fatalf("valid hosted/token card order rejected: %v", err)
	}
	for name, mutate := range map[string]func(*PaymentOrderReceive){
		"missing reference": func(request *PaymentOrderReceive) { request.PaymentMethodTokenReference = "" },
		"PAN metadata": func(request *PaymentOrderReceive) {
			request.Metadata = JSONMap{"nested": JSONMap{"card_number": "4111" + "1111" + "1111" + "1111"}}
		},
		"CVC metadata":  func(request *PaymentOrderReceive) { request.Metadata = JSONMap{"cvc": "123"} },
		"OTP metadata":  func(request *PaymentOrderReceive) { request.Metadata = JSONMap{"otp": "456789"} },
		"PAN reference": func(request *PaymentOrderReceive) { request.PaymentMethodTokenReference = "4111-1111-1111-1111" },
	} {
		t.Run(name, func(t *testing.T) {
			request := valid
			request.MerchantOrderID = "invalid_" + strings.ReplaceAll(name, " ", "_")
			mutate(&request)
			if _, err := service.ReceiveOrder(context.Background(), "tenant", "project", request); err == nil {
				t.Fatal("expected card safety validation error")
			}
		})
	}
}

func TestPaymentDomainNotificationRefundBillLifecycleAndIsolation(t *testing.T) {
	service := newPaymentDomainTestService(t)
	ctx := context.Background()
	order := testPaymentOrder(PaymentProviderWeChatPay, "merchant_a", "order_shared")
	if _, err := service.ReceiveOrder(ctx, "tenant_a", "project_a", order); err != nil {
		t.Fatal(err)
	}
	other := order
	other.MerchantID = "merchant_b"
	if _, err := service.ReceiveOrder(ctx, "tenant_a", "project_a", other); err != nil {
		t.Fatal(err)
	}
	notification := PaymentNotificationReceive{
		Provider: PaymentProviderWeChatPay, MerchantID: "merchant_a", ProviderEventID: "event_success",
		EventType: "TRANSACTION.SUCCESS", ResourceType: "order", MerchantOrderID: "order_shared",
		ProviderObjectID: "wx_order_1", ProviderStatus: "SUCCESS", PayloadSHA256: testPaymentPayloadHash,
	}
	received, err := receiveVerifiedPaymentNotificationForTest(t, service, ctx, "tenant_a", "project_a", notification)
	if err != nil || !received.Result.Applied || received.Result.NormalizedStatus != PaymentOrderStatusSucceeded {
		t.Fatalf("notification receive: %#v err=%v", received, err)
	}
	replay, err := receiveVerifiedPaymentNotificationForTest(t, service, ctx, "tenant_a", "project_a", notification)
	if err != nil || !replay.IdempotentReplay {
		t.Fatalf("notification replay: %#v err=%v", replay, err)
	}
	orderA, _ := service.GetOrder(ctx, "tenant_a", "project_a", "merchant_a", PaymentProviderWeChatPay, "order_shared")
	orderB, _ := service.GetOrder(ctx, "tenant_a", "project_a", "merchant_b", PaymentProviderWeChatPay, "order_shared")
	if orderA.Result.Status != PaymentOrderStatusSucceeded || orderB.Result.Status != PaymentOrderStatusCreated {
		t.Fatalf("merchant isolation failed: A=%#v B=%#v", orderA.Result, orderB.Result)
	}
	refund, err := service.ReceiveRefund(ctx, "tenant_a", "project_a", PaymentRefundReceive{
		Provider: PaymentProviderWeChatPay, MerchantID: "merchant_a", MerchantRefundID: "refund_1",
		MerchantOrderID: "order_shared", Amount: 500, Currency: "CNY",
	})
	if err != nil || refund.Result.Status != PaymentRefundStatusCreated {
		t.Fatalf("refund receive: %#v err=%v", refund, err)
	}
	refundEvent := PaymentNotificationReceive{
		Provider: PaymentProviderWeChatPay, MerchantID: "merchant_a", ProviderEventID: "refund_event",
		EventType: "REFUND.SUCCESS", ResourceType: "refund", MerchantRefundID: "refund_1",
		ProviderObjectID: "wx_refund_1", ProviderStatus: "SUCCESS", PayloadSHA256: testPaymentHeadersHash,
	}
	if _, err := receiveVerifiedPaymentNotificationForTest(t, service, ctx, "tenant_a", "project_a", refundEvent); err != nil {
		t.Fatal(err)
	}
	bill, err := service.ReceiveBillEntry(ctx, "tenant_a", "project_a", PaymentBillEntryReceive{
		Provider: PaymentProviderWeChatPay, MerchantID: "merchant_a", BillEntryID: "bill_refund",
		BillDate: "2026-07-10", BillKind: "refund", MerchantRefundID: "refund_1",
		Amount: 500, Currency: "CNY", ProviderStatus: "SUCCESS", SourceSHA256: testPaymentFailureHash,
	})
	if err != nil || bill.Result.MatchStatus != PaymentBillMatchMatched {
		t.Fatalf("refund bill reconcile: %#v err=%v", bill, err)
	}
	conflictBill, err := service.ReceiveBillEntry(ctx, "tenant_a", "project_a", PaymentBillEntryReceive{
		Provider: PaymentProviderWeChatPay, MerchantID: "merchant_a", BillEntryID: "bill_conflict",
		BillDate: "2026-07-10", BillKind: "transaction", MerchantOrderID: "order_shared",
		Amount: 999, Currency: "CNY", ProviderStatus: "SUCCESS", SourceSHA256: testPaymentHeadersHash,
	})
	if err != nil || conflictBill.Result.MatchStatus != PaymentBillMatchConflict {
		t.Fatalf("conflict bill reconcile: %#v err=%v", conflictBill, err)
	}
}

func TestPaymentDomainIdempotencyConflictTerminalTransitionAndConcurrency(t *testing.T) {
	service := newPaymentDomainTestService(t)
	ctx := context.Background()
	request := testPaymentOrder(PaymentProviderAlipay, "merchant", "order_concurrent")
	request.Channel = "app"
	const workers = 32
	var wg sync.WaitGroup
	replays := 0
	var mu sync.Mutex
	errs := make(chan error, workers)
	for index := 0; index < workers; index++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			result, err := service.ReceiveOrder(ctx, "tenant", "project", request)
			if err != nil {
				errs <- err
				return
			}
			if result.IdempotentReplay {
				mu.Lock()
				replays++
				mu.Unlock()
			}
		}()
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		t.Fatal(err)
	}
	if replays != workers-1 {
		t.Fatalf("replays = %d, want %d", replays, workers-1)
	}
	conflict := request
	conflict.Amount++
	_, err := service.ReceiveOrder(ctx, "tenant", "project", conflict)
	var domainConflict PaymentDomainConflictError
	if !errors.As(err, &domainConflict) {
		t.Fatalf("expected order conflict, got %v", err)
	}
	success := PaymentNotificationReceive{
		Provider: PaymentProviderAlipay, MerchantID: "merchant", ProviderEventID: "event_terminal",
		EventType: "trade_status_sync", ResourceType: "order", MerchantOrderID: "order_concurrent",
		ProviderStatus: "TRADE_SUCCESS", PayloadSHA256: testPaymentPayloadHash,
	}
	if _, err := receiveVerifiedPaymentNotificationForTest(t, service, ctx, "tenant", "project", success); err != nil {
		t.Fatal(err)
	}
	closed := success
	closed.ProviderEventID, closed.ProviderStatus, closed.PayloadSHA256 = "event_late_close", "TRADE_CLOSED", testPaymentHeadersHash
	if _, err := receiveVerifiedPaymentNotificationForTest(t, service, ctx, "tenant", "project", closed); err == nil {
		t.Fatal("terminal succeeded order accepted closed transition")
	}
}

func TestPaymentDomainPublicNotificationFailsClosedWithoutSideEffects(t *testing.T) {
	service := newPaymentDomainTestService(t)
	ctx := context.Background()
	if _, err := service.ReceiveOrder(ctx, "tenant", "project", testPaymentOrder(PaymentProviderWeChatPay, "merchant", "order_public")); err != nil {
		t.Fatal(err)
	}
	attack := PaymentNotificationReceive{
		Provider: PaymentProviderWeChatPay, MerchantID: "merchant", ProviderEventID: "event_forged",
		EventType: "TRANSACTION.SUCCESS", ResourceType: "order", MerchantOrderID: "order_public",
		ProviderStatus: "SUCCESS", PayloadSHA256: testPaymentPayloadHash,
	}
	_, err := service.ReceiveNotification(ctx, "tenant", "project", attack)
	var required PaymentNotificationVerificationRequiredError
	if !errors.As(err, &required) {
		t.Fatalf("expected verification requirement, got %T %v", err, err)
	}
	order, err := service.GetOrder(ctx, "tenant", "project", "merchant", PaymentProviderWeChatPay, "order_public")
	if err != nil || order.Result.Status != PaymentOrderStatusCreated || order.Result.ProviderStatus != "" {
		t.Fatalf("forged notification changed order: %#v err=%v", order.Result, err)
	}
	events, err := service.ListNotifications(ctx, "tenant", "project", "merchant", PaymentProviderWeChatPay, 100)
	if err != nil || events.Result.Count != 0 {
		t.Fatalf("forged notification persisted: %#v err=%v", events.Result, err)
	}
}

func TestPaymentDomainSealedVerificationArtifactRejectsTampering(t *testing.T) {
	service := newPaymentDomainTestService(t)
	ctx := context.Background()
	if _, err := service.ReceiveOrder(ctx, "tenant", "project", testPaymentOrder(PaymentProviderWeChatPay, "merchant", "order_bound")); err != nil {
		t.Fatal(err)
	}
	request := PaymentNotificationReceive{
		Provider: PaymentProviderWeChatPay, MerchantID: "merchant", ProviderEventID: "event_bound",
		EventType: "TRANSACTION.SUCCESS", ResourceType: "order", MerchantOrderID: "order_bound",
		ProviderStatus: "SUCCESS", PayloadSHA256: testPaymentPayloadHash,
	}
	sealed, err := service.issueVerifiedPaymentNotification(request, paymentVerificationEvidence{
		VerifierID: "wechatpay.api-v3", VerifierVersion: "0.1.0-plan-only",
		AcquirerReference: "merchant-binding-ref", SignatureSHA256: testPaymentFailureHash,
		ProviderTimestamp: "1783658400", ProviderNonce: "nonce-bound",
		CertificateKeyRef: "wechatpay-platform-cert:test-serial",
	})
	if err != nil {
		t.Fatal(err)
	}
	if sealed.artifact.ArtifactMACSHA256 == "" || sealed.artifact.RawBodySHA256 != request.PayloadSHA256 ||
		sealed.artifact.RawPayloadIncluded || sealed.artifact.SecretValuePresent {
		t.Fatalf("unsafe verification artifact: %#v", sealed.artifact)
	}
	for name, mutate := range map[string]func(*sealedPaymentNotification){
		"merchant":  func(value *sealedPaymentNotification) { value.request.MerchantID = "attacker" },
		"provider":  func(value *sealedPaymentNotification) { value.request.Provider = PaymentProviderAlipay },
		"event":     func(value *sealedPaymentNotification) { value.request.ProviderEventID = "other" },
		"status":    func(value *sealedPaymentNotification) { value.request.ProviderStatus = "CLOSED" },
		"body hash": func(value *sealedPaymentNotification) { value.request.PayloadSHA256 = testPaymentHeadersHash },
		"verifier":  func(value *sealedPaymentNotification) { value.artifact.VerifierID = "attacker" },
		"mac":       func(value *sealedPaymentNotification) { value.artifact.ArtifactMACSHA256 = testPaymentHeadersHash },
	} {
		t.Run(name, func(t *testing.T) {
			tampered := sealed
			mutate(&tampered)
			if _, err := service.receiveVerifiedNotification(ctx, "tenant", "project", tampered); err == nil {
				t.Fatal("tampered notification accepted")
			}
		})
	}
	order, err := service.GetOrder(ctx, "tenant", "project", "merchant", PaymentProviderWeChatPay, "order_bound")
	if err != nil || order.Result.Status != PaymentOrderStatusCreated {
		t.Fatalf("tampering changed order: %#v err=%v", order.Result, err)
	}
}

func TestPaymentDomainPublicJSONAndSchemaAreSafeAndMerchantScoped(t *testing.T) {
	service := newPaymentDomainTestService(t)
	request := testPaymentOrder(PaymentProviderDomesticBankCard, "merchant", "safe_order")
	request.Channel, request.AcquirerReference = "acquirer_hosted", "hosted_session_ref"
	result, err := service.ReceiveOrder(context.Background(), "tenant", "project", request)
	if err != nil {
		t.Fatal(err)
	}
	payload, err := json.Marshal(result)
	if err != nil {
		t.Fatal(err)
	}
	serialized := strings.ToLower(string(payload))
	for _, forbidden := range []string{`"pan"`, `"card_number"`, `"cvc"`, `"cvv"`, `"otp"`, `"raw_payload"`} {
		if strings.Contains(serialized, forbidden) {
			t.Fatalf("public output contains forbidden material %q: %s", forbidden, serialized)
		}
	}
	for _, required := range []string{
		"PRIMARY KEY (tenant_id, project_id, merchant_id, provider, merchant_order_id)",
		"PRIMARY KEY (tenant_id, project_id, merchant_id, provider, merchant_refund_id)",
		"PRIMARY KEY (tenant_id, project_id, merchant_id, provider, provider_event_id)",
		"PRIMARY KEY (tenant_id, project_id, merchant_id, provider, bill_entry_id)",
	} {
		if !strings.Contains(PaymentDomainSchemaSQL, required) {
			t.Fatalf("schema missing %q", required)
		}
	}
}
