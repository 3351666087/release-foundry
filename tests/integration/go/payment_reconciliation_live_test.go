package gointegration

import (
	"context"
	"errors"
	"fmt"
	"os"
	"testing"
	"time"

	ashrclone "github.com/ashr-labs/ashr/packages/go/ashrclone"
)

func TestPostgresPaymentReconciliationLiveOptIn(t *testing.T) {
	dsn := os.Getenv("A1_POSTGRES_TEST_DSN")
	if dsn == "" {
		t.Skip("set A1_POSTGRES_TEST_DSN to run live Postgres payment reconciliation proof")
	}
	ctx := context.Background()
	repository, err := ashrclone.OpenPostgresRepository(dsn)
	if err != nil {
		t.Fatalf("open postgres repository: %v", err)
	}
	defer repository.Close()
	if err := repository.Migrate(ctx); err != nil {
		t.Fatalf("migrate base postgres repository: %v", err)
	}
	if err := repository.MigratePaymentReconciliation(ctx); err != nil {
		t.Fatalf("migrate payment reconciliation repository: %v", err)
	}
	service, err := ashrclone.NewPaymentReconciliationService(repository)
	if err != nil {
		t.Fatal(err)
	}

	suffix := fmt.Sprintf("%d", time.Now().UTC().UnixNano())
	tenantID := "tenant_payment_live_" + suffix
	projectID := "project_payment_live_" + suffix
	if _, err := repository.BootstrapProject("Payment Live Tenant", "Payment Live Project", ashrclone.Dataset{Name: "Payment Live Dataset"}, tenantID, projectID); err != nil {
		t.Fatalf("bootstrap project: %v", err)
	}
	eventID := "evt_payment_live_" + suffix
	envelope := ashrclone.PaymentEventHashEnvelope{
		Provider: "stripe", ProviderEventID: eventID, EventType: "invoice.paid",
		PayloadSHA256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		HeadersSHA256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
	}
	received, err := service.Receive(ctx, tenantID, projectID, envelope)
	if err != nil || received.IdempotentReplay || received.Result.Status != ashrclone.PaymentEventStatusReceived {
		t.Fatalf("receive: result=%#v err=%v", received, err)
	}
	replay, err := service.Receive(ctx, tenantID, projectID, envelope)
	if err != nil || !replay.IdempotentReplay {
		t.Fatalf("receive replay: result=%#v err=%v", replay, err)
	}
	conflicting := envelope
	conflicting.PayloadSHA256 = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
	_, err = service.Receive(ctx, tenantID, projectID, conflicting)
	var conflict ashrclone.PaymentReconciliationConflictError
	if !errors.As(err, &conflict) {
		t.Fatalf("expected durable hash conflict, got %v", err)
	}
	if _, err := service.Verify(ctx, tenantID, projectID, "stripe", eventID); err != nil {
		t.Fatalf("verify: %v", err)
	}
	applied, err := service.Apply(ctx, tenantID, projectID, "stripe", eventID)
	if err != nil || applied.Result.Status != ashrclone.PaymentEventStatusApplied {
		t.Fatalf("apply: result=%#v err=%v", applied, err)
	}
	isolated, err := service.List(ctx, tenantID, "wrong_project", "", 100)
	if err != nil {
		t.Fatalf("isolated list: %v", err)
	}
	if isolated.Result.Count != 0 {
		t.Fatalf("cross-project event leak: %#v", isolated.Result)
	}
}
