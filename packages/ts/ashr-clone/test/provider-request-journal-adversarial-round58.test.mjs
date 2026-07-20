import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  PROVIDER_REQUEST_JOURNAL_SCHEMA_VERSION,
  ProviderRequestJournal,
  ProviderRequestJournalError,
  ProviderStreamLedger,
  providerRequestFingerprint,
  requestModalityEvidence,
} from "../dist/index.js";

const scope = {
  tenantId: "round58-tenant-secret",
  projectId: "round58-project-secret",
  provider: "round58-provider-secret",
  model: "round58-model-secret",
  operation: "responses.create",
};

const messages = [{
  role: "user",
  parts: [
    { type: "text", text: "ROUND58_RAW_PROMPT_MUST_NOT_PERSIST" },
    {
      type: "image",
      url: "https://media.invalid/image.png?signature=ROUND58_IMAGE_URL_SECRET",
      media_type: "image/png",
    },
    { type: "audio", data: "ROUND58_RAW_AUDIO_BYTES", media_type: "audio/wav" },
    {
      type: "file",
      path: "C:/round58/ROUND58_RAW_FILE.pdf",
      filename: "ROUND58_SECRET_FILENAME.pdf",
      media_type: "application/pdf",
    },
    {
      type: "video",
      url: "https://media.invalid/video.mp4?signature=ROUND58_VIDEO_URL_SECRET",
      media_type: "video/mp4",
    },
  ],
}];

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function waitFor(predicate, description, timeoutMs = 2_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = predicate();
    if (value) {
      return value;
    }
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  assert.fail(`${description} was not observed within ${timeoutMs}ms`);
}

function runningSnapshot({
  requestMessages = messages,
  requestScope = scope,
  leaseExpiresAt = "2026-07-12T00:30:00.000Z",
  fencingToken = 7,
} = {}) {
  const requestFingerprint = providerRequestFingerprint(requestScope, requestMessages);
  const journalKey = "a".repeat(64);
  const partEvidence = requestModalityEvidence(requestMessages);
  return {
    journalKey,
    snapshot: {
      schema_version: PROVIDER_REQUEST_JOURNAL_SCHEMA_VERSION,
      entries: {
        [journalKey]: {
          schema_version: PROVIDER_REQUEST_JOURNAL_SCHEMA_VERSION,
          entry_id: journalKey,
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
          lease_expires_at: leaseExpiresAt,
          fencing_token: fencingToken,
          stream_observed: false,
          stream_snapshot: null,
          part_evidence: partEvidence,
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
    },
  };
}

test("restart converts running to indeterminate and clears its lease", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-round58-restart-"));
  const path = join(temp, "journal.json");
  try {
    const seeded = runningSnapshot();
    writeFileSync(path, JSON.stringify(seeded.snapshot), "utf8");
    const journal = await ProviderRequestJournal.open(path, {
      clock: () => new Date("2026-07-12T00:01:00.000Z"),
    });
    const recovered = journal.get(seeded.journalKey);
    assert.equal(recovered.state, "indeterminate");
    assert.equal(recovered.recovery_count, 1);
    assert.equal(recovered.lease_owner_sha256, null);
    assert.equal(recovered.lease_expires_at, null);
    assert.equal(recovered.error_evidence.kind, "restart_recovery");
    assert.equal(recovered.error_evidence.retryable, false);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("stale lease fails closed without executing a second provider request", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-round58-stale-"));
  const path = join(temp, "journal.json");
  let now = new Date("2026-07-12T00:00:00.000Z");
  const release = deferred();
  try {
    const journal = await ProviderRequestJournal.open(path, { clock: () => now });
    const active = journal.run({
      scope,
      idempotencyKey: "round58-stale-key",
      messages,
      leaseOwner: "round58-worker-a-secret",
      leaseDurationMs: 1_000,
      execute: async () => {
        await release.promise;
        return { finishReason: "stop" };
      },
    });
    await waitFor(() => journal.list()[0]?.state === "in_flight", "in-flight journal state");
    now = new Date("2026-07-12T00:00:02.000Z");
    release.resolve();
    await assert.rejects(
      active,
      (error) => error instanceof ProviderRequestJournalError && error.code === "indeterminate",
    );
    let secondExecutions = 0;
    await assert.rejects(
      journal.run({
        scope,
        idempotencyKey: "round58-stale-key",
        messages,
        leaseOwner: "round58-worker-b-secret",
        execute: async () => {
          secondExecutions += 1;
          return { finishReason: "unsafe" };
        },
      }),
      (error) => error instanceof ProviderRequestJournalError && error.code === "indeterminate",
    );
    assert.equal(secondExecutions, 0);
    assert.equal(journal.list()[0].state, "indeterminate");
    assert.equal(journal.list()[0].error_evidence.kind, "stale_claim");
  } finally {
    release.resolve();
    rmSync(temp, { recursive: true, force: true });
  }
});

test("partial stream consumption blocks retry and retry reconciliation", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-round58-stream-"));
  const path = join(temp, "journal.json");
  try {
    const journal = await ProviderRequestJournal.open(path);
    let attempts = 0;
    await assert.rejects(
      journal.run({
        scope,
        idempotencyKey: "round58-stream-key",
        messages,
        maxAttempts: 5,
        execute: async ({ markStreamObserved, journalKey, fencingToken }) => {
          attempts += 1;
          const stream = new ProviderStreamLedger(undefined, {
            entry_id: journalKey,
            fencing_token: fencingToken,
          });
          stream.observe(0, "delta", "ROUND58_STREAMED_SECRET_OUTPUT");
          await markStreamObserved(stream.snapshot());
          const error = new Error("ROUND58_STREAMED_SECRET_OUTPUT");
          error.retryable = true;
          throw error;
        },
      }),
      (error) => error instanceof ProviderRequestJournalError && error.code === "indeterminate",
    );
    assert.equal(attempts, 1);
    const entry = journal.list()[0];
    assert.equal(entry.state, "indeterminate");
    assert.equal(entry.stream_observed, true);
    await assert.rejects(
      journal.reconcile(entry.journal_key, {
        outcome: "retry",
        reason: "ROUND58_OPERATOR_REASON_MUST_BE_HASHED",
      }),
      (error) => error instanceof ProviderRequestJournalError && error.code === "indeterminate",
    );
    const raw = readFileSync(path, "utf8");
    assert.equal(raw.includes("ROUND58_STREAMED_SECRET_OUTPUT"), false);
    assert.equal(raw.includes("ROUND58_OPERATOR_REASON_MUST_BE_HASHED"), false);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("scope fingerprint isolates tenant project provider model and operation", () => {
  const variants = [
    scope,
    { ...scope, tenantId: "tenant-other" },
    { ...scope, projectId: "project-other" },
    { ...scope, provider: "provider-other" },
    { ...scope, model: "model-other" },
    { ...scope, operation: "audio.transcriptions.create" },
  ];
  const fingerprints = variants.map((variant) => providerRequestFingerprint(variant, messages));
  assert.equal(new Set(fingerprints).size, variants.length);
});

test("five modalities retain equal safe evidence without raw secret prompt URL or media persistence", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-round58-privacy-"));
  const path = join(temp, "journal.json");
  try {
    const journal = await ProviderRequestJournal.open(path);
    const result = await journal.run({
      scope,
      idempotencyKey: "ROUND58_RAW_IDEMPOTENCY_SECRET",
      messages,
      leaseOwner: "ROUND58_RAW_LEASE_OWNER_SECRET",
      execute: async () => ({
        finishReason: "stop",
        providerRequestId: "ROUND58_RAW_PROVIDER_REQUEST_ID",
        metadata: {
          region: "cn-east",
          prompt: "ROUND58_RAW_RESPONSE_PROMPT",
          endpoint: "https://provider.invalid?token=ROUND58_RESPONSE_URL_SECRET",
          authorization: "Bearer ROUND58_RESPONSE_BEARER_SECRET",
        },
      }),
    });
    assert.deepEqual(
      result.entry.modality_evidence.map((item) => item.type),
      ["text", "image", "audio", "file", "video"],
    );
    for (const evidence of result.entry.modality_evidence) {
      assert.equal(evidence.content_sha256.length, 64);
      assert.ok(evidence.byte_length > 0);
    }
    assert.deepEqual(result.entry.completion_evidence.metadata, { region: "cn-east" });

    const raw = readFileSync(path, "utf8");
    for (const forbidden of [
      "round58-tenant-secret",
      "round58-project-secret",
      "round58-provider-secret",
      "round58-model-secret",
      "ROUND58_RAW_IDEMPOTENCY_SECRET",
      "ROUND58_RAW_LEASE_OWNER_SECRET",
      "ROUND58_RAW_PROMPT_MUST_NOT_PERSIST",
      "ROUND58_IMAGE_URL_SECRET",
      "ROUND58_RAW_AUDIO_BYTES",
      "ROUND58_RAW_FILE.pdf",
      "ROUND58_SECRET_FILENAME.pdf",
      "ROUND58_VIDEO_URL_SECRET",
      "ROUND58_RAW_PROVIDER_REQUEST_ID",
      "ROUND58_RAW_RESPONSE_PROMPT",
      "ROUND58_RESPONSE_URL_SECRET",
      "ROUND58_RESPONSE_BEARER_SECRET",
      "media.invalid",
    ]) {
      assert.equal(raw.includes(forbidden), false, `persisted forbidden material: ${forbidden}`);
    }
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("same-process concurrent claim executes exactly one owner", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-round58-concurrent-"));
  const path = join(temp, "journal.json");
  const release = deferred();
  try {
    const journal = await ProviderRequestJournal.open(path);
    let executions = 0;
    const first = journal.run({
      scope,
      idempotencyKey: "round58-concurrent-key",
      messages,
      leaseOwner: "worker-a",
      execute: async () => {
        executions += 1;
        await release.promise;
        return { finishReason: "first" };
      },
    });
    const second = journal.run({
      scope,
      idempotencyKey: "round58-concurrent-key",
      messages,
      leaseOwner: "worker-b",
      execute: async () => {
        executions += 1;
        return { finishReason: "second" };
      },
    });
    await waitFor(() => executions === 1, "single provider execution");
    const observedExecutions = executions;
    release.resolve();
    const settled = await Promise.allSettled([first, second]);
    assert.equal(observedExecutions, 1);
    assert.equal(settled.filter((item) => item.status === "fulfilled").length, 2);
    const results = settled.map((item) => item.value);
    assert.equal(results.filter((item) => item.executed).length, 1);
    assert.equal(results.filter((item) => item.replayed).length, 1);
  } finally {
    release.resolve();
    rmSync(temp, { recursive: true, force: true });
  }
});

test("expired completion is fenced before a reconciled owner receives the next token", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-round58-fencing-"));
  const path = join(temp, "journal.json");
  const firstRelease = deferred();
  let now = new Date("2026-07-12T00:00:00.000Z");
  try {
    const journal = await ProviderRequestJournal.open(path, { clock: () => now });
    const first = journal.run({
      scope,
      idempotencyKey: "round58-fencing-key",
      messages,
      leaseOwner: "worker-a",
      leaseDurationMs: 1_000,
      execute: async ({ fencingToken }) => {
        assert.equal(fencingToken, 1);
        await firstRelease.promise;
        return { finishReason: "obsolete-owner" };
      },
    });
    await waitFor(() => journal.list()[0]?.state === "in_flight", "in-flight journal state");
    now = new Date("2026-07-12T00:00:02.000Z");
    firstRelease.resolve();
    await assert.rejects(
      first,
      (error) => error instanceof ProviderRequestJournalError && error.code === "indeterminate",
    );
    const indeterminate = journal.list()[0];
    assert.equal(indeterminate.error_evidence.kind, "stale_claim");
    await journal.reconcile(indeterminate.journal_key, {
      outcome: "retry",
      reason: "provider confirms worker-a request was not accepted",
    });
    const second = await journal.run({
      scope,
      idempotencyKey: "round58-fencing-key",
      messages,
      leaseOwner: "worker-b",
      execute: async ({ fencingToken }) => {
        assert.equal(fencingToken, 2);
        return { finishReason: "current-owner" };
      },
    });
    assert.equal(second.entry.completion_evidence.finish_reason, "current-owner");
    assert.equal(journal.list()[0].completion_evidence.finish_reason, "current-owner");
  } finally {
    firstRelease.resolve();
    rmSync(temp, { recursive: true, force: true });
  }
});
