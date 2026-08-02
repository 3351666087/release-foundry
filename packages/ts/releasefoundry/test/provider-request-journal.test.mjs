import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";

import {
  PROVIDER_REQUEST_JOURNAL_SCHEMA_VERSION,
  ProviderStreamLedger,
  ProviderRequestJournal,
  ProviderRequestJournalError,
  providerRequestFingerprint,
  requestModalityEvidence,
} from "../dist/index.js";

const scope = {
  tenantId: "tenant-a",
  projectId: "project-a",
  provider: "openai-compatible",
  model: "commercial-model",
};

const messages = [{
  role: "user",
  parts: [
    { type: "text", text: "private prompt that must never persist" },
    { type: "image", url: "https://signed.example/image?token=secret", media_type: "image/png" },
    { type: "audio", data: "private-audio", media_type: "audio/wav" },
    { type: "file", path: "C:/private/report.pdf", media_type: "application/pdf", filename: "secret-report.pdf" },
    { type: "video", data: new Uint8Array([1, 2, 3]), media_type: "video/mp4" },
  ],
}];

async function waitForState(journal, expected, timeoutMs = 2_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const entry = journal.list()[0];
    if (entry?.state === expected) {
      return entry;
    }
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  assert.fail(`journal did not reach ${expected} within ${timeoutMs}ms`);
}

test("journal persists only safe five-modality evidence and replays success after restart", async () => {
  const temp = mkdtempSync(join(tmpdir(), "releasefoundry-provider-journal-"));
  const path = join(temp, "journal.json");
  try {
    let calls = 0;
    const journal = await ProviderRequestJournal.open(path);
    const first = await journal.run({
      scope,
      idempotencyKey: "customer-visible-idempotency-key",
      messages,
      execute: async () => {
        calls += 1;
        return {
          usage: { input_tokens: 15, output_tokens: 7, total_tokens: 22, cached_input_tokens: 3 },
          finishReason: "tool_calls",
          toolCalls: [{ id: "provider-call-secret", name: "lookup", arguments: { query: "private argument" } }],
          providerRequestId: "provider-request-secret",
          metadata: {
            region: "cn-east",
            endpoint: "https://provider.example/v1/chat",
            authorization: "Bearer hidden",
            prompt: "hidden",
          },
        };
      },
    });

    assert.equal(first.replayed, false);
    assert.equal(first.entry.state, "succeeded");
    assert.equal(first.entry.entry_id, first.entry.journal_key);
    assert.equal(first.entry.attempt_count, first.entry.attempts);
    assert.equal(first.entry.modality_evidence.length, 5);
    assert.deepEqual(first.entry.modality_evidence.map((item) => item.type), ["text", "image", "audio", "file", "video"]);
    assert.equal(first.entry.usage_evidence.total_tokens, 22);
    assert.equal(first.entry.completion_evidence.tool_call_count, 1);
    assert.deepEqual(first.entry.completion_evidence.metadata, { region: "cn-east" });

    const raw = readFileSync(path, "utf8");
    const persisted = JSON.parse(raw);
    const persistedEntry = Object.values(persisted.entries)[0];
    assert.equal(persistedEntry.state, "succeeded");
    assert.equal(typeof persistedEntry.entry_id, "string");
    assert.equal(persistedEntry.attempt_count, 1);
    assert.deepEqual(persistedEntry.request_evidence.modalities_present, ["text", "image", "audio", "file", "video"]);
    assert.deepEqual(persistedEntry.persistence_capabilities, {
      storage_kind: "local_json_file",
      restart_persistent: true,
      atomic_replace: true,
      same_process_identity_claim: true,
      cross_process_lock: false,
      multi_process_safe: false,
      multi_host_safe: false,
      power_loss_durability_proven: false,
      crash_recovery: "in_flight_to_indeterminate",
    });
    for (const legacyField of ["journal_key", "attempts", "lease_owner_sha256", "modality_evidence"]) {
      assert.equal(Object.hasOwn(persistedEntry, legacyField), false);
    }
    for (const forbidden of [
      "private prompt", "signed.example", "token=secret", "private-audio", "C:/private",
      "secret-report", "private argument", "provider-call-secret", "provider-request-secret",
      "customer-visible-idempotency-key", "provider.example", "Bearer hidden",
    ]) {
      assert.equal(raw.includes(forbidden), false, `persisted forbidden value: ${forbidden}`);
    }

    const restarted = await ProviderRequestJournal.open(path);
    const replay = await restarted.run({
      scope,
      idempotencyKey: "customer-visible-idempotency-key",
      messages,
      execute: async () => {
        calls += 1;
        throw new Error("must not execute a durable replay");
      },
    });
    assert.equal(replay.replayed, true);
    assert.equal(replay.executed, false);
    assert.equal(calls, 1);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("retryable failure is persisted before retry and terminal failure is durable", async () => {
  const temp = mkdtempSync(join(tmpdir(), "releasefoundry-provider-retry-"));
  const path = join(temp, "journal.json");
  try {
    const journal = await ProviderRequestJournal.open(path);
    let attempts = 0;
    const result = await journal.run({
      scope,
      idempotencyKey: "retry-key",
      messages: [{ role: "user", content: "retry me" }],
      maxAttempts: 2,
      execute: async ({ attempt }) => {
        attempts = attempt;
        if (attempt === 1) {
          const error = new Error("temporary secret-bearing failure");
          error.retryable = true;
          error.statusCode = 429;
          throw error;
        }
        return { usage: { input_tokens: 2, output_tokens: 1 }, finishReason: "stop" };
      },
    });
    assert.equal(attempts, 2);
    assert.equal(result.entry.attempts, 2);
    assert.equal(result.entry.state, "succeeded");

    await assert.rejects(
      journal.run({
        scope,
        idempotencyKey: "terminal-key",
        messages: [{ role: "user", content: "fail me" }],
        maxAttempts: 1,
        execute: async () => {
          const error = new Error("invalid request with secret");
          error.retryable = false;
          error.statusCode = 400;
          throw error;
        },
      }),
      /invalid request/,
    );
    const snapshot = JSON.parse(readFileSync(path, "utf8"));
    const terminal = Object.values(snapshot.entries).find((entry) => entry.state === "failed_terminal");
    assert.equal(terminal.error_evidence.status_code, 400);
    assert.equal(terminal.error_evidence.retryable, false);
    assert.equal(JSON.stringify(terminal).includes("invalid request"), false);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("restart converts an interrupted five-modality request into fail-closed indeterminate", async () => {
  const temp = mkdtempSync(join(tmpdir(), "releasefoundry-provider-recovery-"));
  const path = join(temp, "journal.json");
  try {
    const requestFingerprint = providerRequestFingerprint(scope, [{ role: "user", content: "recover" }]);
    const seed = {
      schema_version: PROVIDER_REQUEST_JOURNAL_SCHEMA_VERSION,
      entries: {
        journal: {
          schema_version: PROVIDER_REQUEST_JOURNAL_SCHEMA_VERSION,
          entry_id: "a".repeat(64),
          scope_fingerprint: "b".repeat(64),
          request_fingerprint: requestFingerprint,
          idempotency_fingerprint: "c".repeat(64),
          request_evidence: {
            modality_counts: { text: 1, image: 1, audio: 1, file: 1, video: 1 },
            modalities_present: ["text", "image", "audio", "file", "video"],
            raw_prompt_persisted: false,
            raw_media_persisted: false,
            raw_url_persisted: false,
            raw_credential_persisted: false,
          },
          state: "in_flight",
          attempt_count: 1,
          max_attempts: 3,
          created_at: "2026-07-12T00:00:00.000Z",
          updated_at: "2026-07-12T00:00:00.000Z",
          next_retry_at: null,
          lease_owner_fingerprint: "d".repeat(64),
          lease_expires_at: "2026-07-12T00:30:00.000Z",
          fencing_token: 7,
          stream_observed: false,
          stream_snapshot: null,
          part_evidence: requestModalityEvidence(messages),
          usage_evidence: null,
          completion_evidence: null,
          error_evidence: null,
          recovery_count: 0,
          persistence_capabilities: {
            storage_kind: "local_json_file",
            restart_persistent: true,
            atomic_replace: true,
            same_process_identity_claim: true,
            cross_process_lock: false,
            multi_process_safe: false,
            multi_host_safe: false,
            power_loss_durability_proven: false,
            crash_recovery: "in_flight_to_indeterminate",
          },
        },
      },
    };
    seed.entries[seed.entries.journal.entry_id] = seed.entries.journal;
    delete seed.entries.journal;
    writeFileSync(path, JSON.stringify(seed), "utf8");
    const journal = await ProviderRequestJournal.open(path, { clock: () => new Date("2026-07-12T01:00:00.000Z") });
    const recovered = journal.get("a".repeat(64));
    assert.equal(recovered.state, "indeterminate");
    assert.equal(recovered.recovery_count, 1);
    assert.equal(recovered.error_evidence.kind, "restart_recovery");
    assert.equal(recovered.error_evidence.retryable, false);
    assert.equal(recovered.lease_owner_sha256, null);
    assert.deepEqual(recovered.modality_evidence.map((item) => item.type), ["text", "image", "audio", "file", "video"]);
    const approved = await journal.reconcile("a".repeat(64), {
      outcome: "retry",
      reason: "operator confirmed provider did not accept the request",
    });
    assert.equal(approved.state, "retry_wait");
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("expired lease is fenced to indeterminate and explicit reconcile permits retry", async () => {
  const temp = mkdtempSync(join(tmpdir(), "releasefoundry-provider-stale-"));
  const path = join(temp, "journal.json");
  let now = new Date("2026-07-12T00:00:00.000Z");
  let release;
  try {
    const journal = await ProviderRequestJournal.open(path, { clock: () => now });
    const waiting = new Promise((resolve) => { release = resolve; });
    const active = journal.run({
      scope,
      idempotencyKey: "stale-key",
      messages,
      leaseOwner: "worker-a-secret",
      leaseDurationMs: 1_000,
      execute: async () => {
        await waiting;
        return { finishReason: "stop" };
      },
    });
    const running = await waitForState(journal, "in_flight");
    assert.equal(running.fencing_token, 1);
    assert.equal(running.lease_owner_sha256.length, 64);

    now = new Date("2026-07-12T00:00:02.000Z");
    release();
    await assert.rejects(active, (error) => error instanceof ProviderRequestJournalError && error.code === "indeterminate");
    const indeterminate = journal.list()[0];
    assert.equal(indeterminate.state, "indeterminate");
    assert.equal(indeterminate.error_evidence.kind, "stale_claim");

    await journal.reconcile(indeterminate.journal_key, { outcome: "retry", reason: "provider confirms no request was accepted" });
    const replay = await journal.run({
      scope,
      idempotencyKey: "stale-key",
      messages,
      leaseOwner: "worker-b-secret",
      execute: async ({ fencingToken }) => {
        assert.equal(fencingToken, 2);
        return { finishReason: "stop" };
      },
    });
    assert.equal(replay.entry.state, "succeeded");
  } finally {
    release?.();
    rmSync(temp, { recursive: true, force: true });
  }
});

test("observed stream becomes indeterminate and cannot be reconciled to automatic retry", async () => {
  const temp = mkdtempSync(join(tmpdir(), "releasefoundry-provider-stream-"));
  try {
    const journal = await ProviderRequestJournal.open(join(temp, "journal.json"));
    await assert.rejects(
      journal.run({
        scope,
        idempotencyKey: "stream-key",
        messages,
        maxAttempts: 3,
        execute: async ({ markStreamObserved, journalKey, fencingToken }) => {
          const stream = new ProviderStreamLedger(undefined, {
            entry_id: journalKey,
            fencing_token: fencingToken,
          });
          stream.observe(0, "delta", "private streamed output");
          await markStreamObserved(stream.snapshot());
          const error = new Error("connection lost after private streamed output");
          error.retryable = true;
          throw error;
        },
      }),
      (error) => error instanceof ProviderRequestJournalError && error.code === "indeterminate",
    );
    const entry = journal.list()[0];
    assert.equal(entry.state, "indeterminate");
    assert.equal(entry.stream_observed, true);
    assert.equal(entry.error_evidence.kind, "stream_observed");
    await assert.rejects(
      journal.reconcile(entry.journal_key, { outcome: "retry", reason: "operator guessed" }),
      (error) => error instanceof ProviderRequestJournalError && error.code === "indeterminate",
    );
    await assert.rejects(
      journal.reconcile(entry.entry_id, { outcome: "reserved", reason: "operator guessed again" }),
      (error) => error instanceof ProviderRequestJournalError && error.code === "indeterminate",
    );
    const reconciled = await journal.reconcile(entry.journal_key, {
      outcome: "succeeded",
      reason: "provider lookup confirmed completion",
      evidence: { finishReason: "stop", usage: { input_tokens: 9, output_tokens: 4 } },
    });
    assert.equal(reconciled.state, "succeeded");
    assert.equal(reconciled.usage_evidence.total_tokens, 13);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("stream snapshots must be bound to the active entry and fencing token", async () => {
  const temp = mkdtempSync(join(tmpdir(), "releasefoundry-provider-stream-binding-"));
  try {
    const journal = await ProviderRequestJournal.open(join(temp, "journal.json"));
    await assert.rejects(
      journal.run({
        scope,
        idempotencyKey: "unbound-stream-key",
        messages,
        execute: async ({ markStreamObserved }) => {
          const stream = new ProviderStreamLedger();
          stream.observe(0, "delta", "private output");
          await markStreamObserved(stream.snapshot());
          return { finishReason: "stop" };
        },
      }),
      /binding conflicts/,
    );
    await assert.rejects(
      journal.run({
        scope,
        idempotencyKey: "mismatched-stream-key",
        messages,
        execute: async ({ markStreamObserved, journalKey, fencingToken }) => {
          const stream = new ProviderStreamLedger(undefined, {
            entry_id: journalKey,
            fencing_token: fencingToken + 1,
          });
          stream.observe(0, "delta", "private output");
          await markStreamObserved(stream.snapshot());
          return { finishReason: "stop" };
        },
      }),
      /binding conflicts/,
    );
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("partial stream cannot succeed but a bound terminal stream can", async () => {
  const temp = mkdtempSync(join(tmpdir(), "releasefoundry-provider-stream-terminal-"));
  try {
    const partialJournal = await ProviderRequestJournal.open(join(temp, "partial.json"));
    await assert.rejects(
      partialJournal.run({
        scope,
        idempotencyKey: "partial-stream-key",
        messages,
        execute: async ({ markStreamObserved, journalKey, fencingToken }) => {
          const stream = new ProviderStreamLedger(undefined, {
            entry_id: journalKey,
            fencing_token: fencingToken,
          });
          stream.observe(0, "delta", "private output");
          await markStreamObserved(stream.snapshot());
          return { finishReason: "stop" };
        },
      }),
      (error) => error instanceof ProviderRequestJournalError && error.code === "indeterminate",
    );
    assert.equal(partialJournal.list()[0].state, "indeterminate");

    const terminalJournal = await ProviderRequestJournal.open(join(temp, "terminal.json"));
    const result = await terminalJournal.run({
      scope,
      idempotencyKey: "terminal-stream-key",
      messages,
      execute: async ({ markStreamObserved, journalKey, fencingToken }) => {
        const stream = new ProviderStreamLedger(undefined, {
          entry_id: journalKey,
          fencing_token: fencingToken,
        });
        stream.observe(0, "delta", "private output");
        stream.observe(1, "done", { finish_reason: "stop" }, true);
        await markStreamObserved(stream.finalize());
        return { finishReason: "stop" };
      },
    });
    assert.equal(result.entry.state, "succeeded");
    assert.equal(result.entry.stream_snapshot.terminal_observed, true);
    assert.equal(result.entry.stream_snapshot.fencing_token, result.entry.fencing_token);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("same-process concurrent identity calls share one atomic execution claim", async () => {
  const temp = mkdtempSync(join(tmpdir(), "releasefoundry-provider-atomic-"));
  try {
    const journal = await ProviderRequestJournal.open(join(temp, "journal.json"));
    let calls = 0;
    let release;
    let started;
    const waiting = new Promise((resolve) => { release = resolve; });
    const executing = new Promise((resolve) => { started = resolve; });
    const options = {
      scope,
      idempotencyKey: "atomic-key",
      messages,
      execute: async () => {
        calls += 1;
        started();
        await waiting;
        return { finishReason: "stop" };
      },
    };
    const first = journal.run(options);
    const second = journal.run(options);
    await executing;
    assert.equal(calls, 1);
    release();
    const [owner, follower] = await Promise.all([first, second]);
    assert.equal(owner.executed, true);
    assert.equal(follower.executed, false);
    assert.equal(follower.replayed, true);
    assert.equal(owner.entry.entry_id, follower.entry.entry_id);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("fingerprints are scoped, deterministic, modality-sensitive, and reject idempotency conflicts", async () => {
  const base = providerRequestFingerprint(scope, messages);
  assert.equal(base, providerRequestFingerprint(scope, messages));
  assert.notEqual(base, providerRequestFingerprint({ ...scope, tenantId: "tenant-b" }, messages));
  assert.notEqual(base, providerRequestFingerprint(scope, [{ role: "user", parts: [{ type: "audio", data: "different" }] }]));

  const temp = mkdtempSync(join(tmpdir(), "releasefoundry-provider-conflict-"));
  try {
    const journal = await ProviderRequestJournal.open(join(temp, "journal.json"));
    await journal.run({
      scope,
      idempotencyKey: "same-key",
      messages: [{ role: "user", content: "first" }],
      execute: async () => ({ finishReason: "stop" }),
    });
    await assert.rejects(
      journal.run({
        scope,
        idempotencyKey: "same-key",
        messages: [{ role: "user", content: "second" }],
        execute: async () => ({ finishReason: "stop" }),
      }),
      (error) => error instanceof ProviderRequestJournalError && error.code === "idempotency_conflict",
    );
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});
