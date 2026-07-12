package gointegration

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"os"
	"sync"
	"testing"
	"time"

	ashrclone "github.com/ashr-labs/ashr/packages/go/ashrclone"
	_ "github.com/lib/pq"
)

func TestProviderDispatchCoordinatorLiveOptIn(t *testing.T) {
	dsn := os.Getenv("A1_POSTGRES_TEST_DSN")
	if dsn == "" {
		t.Skip("set A1_POSTGRES_TEST_DSN to run live provider dispatch coordination proof")
	}
	repository, err := ashrclone.OpenPostgresRepository(dsn)
	if err != nil {
		t.Fatal(err)
	}
	defer repository.Close()
	if err := repository.Migrate(context.Background()); err != nil {
		t.Fatal(err)
	}

	suffix := fmt.Sprintf("%d", time.Now().UTC().UnixNano())
	tenantID, projectID := "tenant_dispatch_"+suffix, "project_dispatch_"+suffix
	if _, err := repository.BootstrapProject("Dispatch Tenant", "Dispatch Project",
		ashrclone.Dataset{Name: "Dispatch Dataset"}, tenantID, projectID); err != nil {
		t.Fatal(err)
	}
	dispatchID := "dispatch_" + suffix
	request := ashrclone.JSONMap{"model": "qwen", "input_sha256": "request-digest"}
	first, err := repository.SubmitProviderDispatch(tenantID, projectID, "qwen", "chat", request,
		ashrclone.SubmitProviderDispatchOptions{DispatchID: dispatchID})
	if err != nil || first.Result.Status != ashrclone.ProviderDispatchPending {
		t.Fatalf("submit: result=%#v err=%v", first.Result, err)
	}
	replay, err := repository.SubmitProviderDispatch(tenantID, projectID, "qwen", "chat", request,
		ashrclone.SubmitProviderDispatchOptions{DispatchID: dispatchID})
	if err != nil || replay.Result.RequestFingerprint != first.Result.RequestFingerprint {
		t.Fatalf("same-fingerprint replay: result=%#v err=%v", replay.Result, err)
	}
	_, err = repository.SubmitProviderDispatch(tenantID, projectID, "qwen", "chat",
		ashrclone.JSONMap{"model": "qwen", "input_sha256": "different"},
		ashrclone.SubmitProviderDispatchOptions{DispatchID: dispatchID})
	if !errors.Is(err, ashrclone.ErrProviderDispatchConflict) {
		t.Fatalf("expected fingerprint conflict, got %v", err)
	}

	claim1, err := repository.ClaimProviderDispatch(tenantID, projectID, "worker-1",
		ashrclone.ClaimProviderDispatchOptions{Provider: "qwen", Operation: "chat", LeaseSeconds: 60})
	if err != nil || !claim1.Result.Claimed || claim1.Result.Dispatch.FencingToken != 1 {
		t.Fatalf("first claim: result=%#v err=%v", claim1.Result, err)
	}
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`
UPDATE ashr_provider_dispatches SET lease_expires_at=now()-interval '1 second'
WHERE tenant_id=$1 AND project_id=$2 AND dispatch_id=$3`, tenantID, projectID, dispatchID); err != nil {
		_ = db.Close()
		t.Fatal(err)
	}
	_ = db.Close()

	claim2, err := repository.ClaimProviderDispatch(tenantID, projectID, "worker-2",
		ashrclone.ClaimProviderDispatchOptions{Provider: "qwen", Operation: "chat", LeaseSeconds: 60})
	if err != nil || !claim2.Result.Claimed || claim2.Result.Dispatch.FencingToken != 2 {
		t.Fatalf("reclaim: result=%#v err=%v", claim2.Result, err)
	}
	_, err = repository.CompleteProviderDispatch(tenantID, projectID, dispatchID, "worker-1", 1,
		ashrclone.CompleteProviderDispatchOptions{
			Proof:    ashrclone.JSONMap{"receipt": "stale"},
			Response: ashrclone.JSONMap{"output_sha256": "stale"},
		})
	if !errors.Is(err, ashrclone.ErrProviderDispatchFence) {
		t.Fatalf("stale completion was not fenced: %v", err)
	}
	indeterminate, err := repository.MarkProviderDispatchIndeterminate(
		tenantID, projectID, dispatchID, "worker-2", 2, "provider_timeout_after_send",
		ashrclone.JSONMap{"type": "timeout"}, time.Now().UTC())
	if err != nil || indeterminate.Result.Status != ashrclone.ProviderDispatchIndeterminate {
		t.Fatalf("mark indeterminate: result=%#v err=%v", indeterminate.Result, err)
	}
	reconcile, err := repository.ClaimProviderDispatchReconciliation(
		tenantID, projectID, "reconciler-1", ashrclone.ReconcileProviderDispatchOptions{LeaseSeconds: 60})
	if err != nil || !reconcile.Result.Claimed || reconcile.Result.Dispatch.FencingToken != 3 {
		t.Fatalf("reconciliation claim: result=%#v err=%v", reconcile.Result, err)
	}
	streamProof := ashrclone.JSONMap{
		"provider_status":      "succeeded",
		"receipt":              "receipt-" + suffix,
		"stream_digest":        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		"stream_frame_count":   1,
		"stream_fencing_token": 3,
	}
	observed, err := repository.ObserveProviderDispatchStream(
		tenantID, projectID, dispatchID, "reconciler-1", 3,
		ashrclone.ObserveProviderDispatchStreamOptions{
			Stream: streamProof,
		})
	if err != nil || !observed.Result.StreamObserved ||
		observed.Result.StreamObservedFence == nil ||
		*observed.Result.StreamObservedFence != 3 ||
		observed.Result.StreamObservedSHA256 == "" {
		t.Fatalf("observe reconciliation stream: result=%#v err=%v", observed.Result, err)
	}
	completed, err := repository.CompleteProviderDispatch(
		tenantID, projectID, dispatchID, "reconciler-1", 3,
		ashrclone.CompleteProviderDispatchOptions{
			ProviderRequestID: "provider-" + suffix,
			Proof:             streamProof,
			Response:          ashrclone.JSONMap{"output_sha256": "output-" + suffix},
		})
	if err != nil || completed.Result.Status != ashrclone.ProviderDispatchCompleted ||
		completed.Result.TerminalProofSHA256 == "" || completed.Result.TerminalResponseSHA256 == "" {
		t.Fatalf("reconciliation completion: result=%#v err=%v", completed.Result, err)
	}
}

func TestProviderDispatchConcurrentClaimAndRestartLiveOptIn(t *testing.T) {
	dsn := os.Getenv("A1_POSTGRES_TEST_DSN")
	if dsn == "" {
		t.Skip("set A1_POSTGRES_TEST_DSN to run live provider dispatch coordination proof")
	}
	repository, err := ashrclone.OpenPostgresRepository(dsn)
	if err != nil {
		t.Fatal(err)
	}
	if err := repository.Migrate(context.Background()); err != nil {
		_ = repository.Close()
		t.Fatal(err)
	}

	suffix := fmt.Sprintf("%d", time.Now().UTC().UnixNano())
	tenantID, projectID := "tenant_dispatch_race_"+suffix, "project_dispatch_race_"+suffix
	if _, err := repository.BootstrapProject("Dispatch Race Tenant", "Dispatch Race Project",
		ashrclone.Dataset{Name: "Dispatch Race Dataset"}, tenantID, projectID); err != nil {
		_ = repository.Close()
		t.Fatal(err)
	}
	dispatchID := "dispatch_race_" + suffix
	request := ashrclone.JSONMap{"model": "ollama", "input_sha256": "race-request-digest"}
	submitted, err := repository.SubmitProviderDispatch(
		tenantID, projectID, "ollama", "chat", request,
		ashrclone.SubmitProviderDispatchOptions{DispatchID: dispatchID})
	if err != nil {
		_ = repository.Close()
		t.Fatal(err)
	}

	const workers = 16
	start := make(chan struct{})
	results := make(chan ashrclone.ProviderDispatchClaim, workers)
	errorsCh := make(chan error, workers)
	var wait sync.WaitGroup
	for worker := 0; worker < workers; worker++ {
		wait.Add(1)
		go func(worker int) {
			defer wait.Done()
			workerRepository, openErr := ashrclone.OpenPostgresRepository(dsn)
			if openErr != nil {
				errorsCh <- openErr
				return
			}
			defer workerRepository.Close()
			<-start
			claim, claimErr := workerRepository.ClaimProviderDispatch(
				tenantID, projectID, fmt.Sprintf("worker-%02d", worker),
				ashrclone.ClaimProviderDispatchOptions{
					Provider: "ollama", Operation: "chat", LeaseSeconds: 60,
				})
			if claimErr != nil {
				errorsCh <- claimErr
				return
			}
			results <- claim.Result
		}(worker)
	}
	close(start)
	wait.Wait()
	close(results)
	close(errorsCh)
	for claimErr := range errorsCh {
		t.Fatalf("concurrent claim failed: %v", claimErr)
	}
	var winner *ashrclone.ProviderDispatch
	for claim := range results {
		if !claim.Claimed {
			continue
		}
		if winner != nil {
			t.Fatalf("multiple workers claimed one dispatch: first=%#v second=%#v", winner, claim.Dispatch)
		}
		winner = claim.Dispatch
	}
	if winner == nil || winner.DispatchID != dispatchID || winner.FencingToken != 1 {
		t.Fatalf("expected exactly one fenced winner, got %#v", winner)
	}

	streamProof := ashrclone.JSONMap{
		"provider_status":      "succeeded",
		"stream_digest":        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		"stream_frame_count":   2,
		"stream_fencing_token": winner.FencingToken,
	}
	if _, err := repository.ObserveProviderDispatchStream(
		tenantID, projectID, dispatchID, winner.LeaseOwnerID, winner.FencingToken,
		ashrclone.ObserveProviderDispatchStreamOptions{Stream: streamProof}); err != nil {
		t.Fatal(err)
	}
	completed, err := repository.CompleteProviderDispatch(
		tenantID, projectID, dispatchID, winner.LeaseOwnerID, winner.FencingToken,
		ashrclone.CompleteProviderDispatchOptions{
			ProviderRequestID: "ollama-" + suffix,
			Proof:             streamProof,
			Response:          ashrclone.JSONMap{"output_sha256": "race-output-digest"},
		})
	if err != nil {
		t.Fatal(err)
	}
	if err := repository.Close(); err != nil {
		t.Fatal(err)
	}

	restarted, err := ashrclone.OpenPostgresRepository(dsn)
	if err != nil {
		t.Fatal(err)
	}
	defer restarted.Close()
	replayed, err := restarted.SubmitProviderDispatch(
		tenantID, projectID, "ollama", "chat", request,
		ashrclone.SubmitProviderDispatchOptions{DispatchID: dispatchID})
	if err != nil {
		t.Fatal(err)
	}
	if replayed.Result.DispatchID != submitted.Result.DispatchID ||
		replayed.Result.Status != ashrclone.ProviderDispatchCompleted ||
		replayed.Result.TerminalProofSHA256 != completed.Result.TerminalProofSHA256 ||
		replayed.Result.TerminalResponseSHA256 != completed.Result.TerminalResponseSHA256 ||
		!replayed.Result.StreamObserved {
		t.Fatalf("restart replay changed durable dispatch evidence: before=%#v after=%#v",
			completed.Result, replayed.Result)
	}
}
