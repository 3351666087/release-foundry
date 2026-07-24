import assert from "node:assert/strict";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import {
  DurableEventSpool,
  EventBackpressureError,
  EventValidationError,
  PermanentDeliveryError,
  RetryableDeliveryError,
  buildEventEnvelope,
  buildTraceIngestionSender,
  deterministicSample,
  validateEventEnvelope,
} from "../dist/event-spool.js";

const now = "2026-07-24T00:00:00.000Z";

function event({ eventId = "evt_1", purpose = "telemetry", payload = { content: "hello" } } = {}) {
  return buildEventEnvelope({
    tenantId: "tenant_a",
    projectId: "project_a",
    runId: "run_a",
    source: "sdk",
    eventType: "trace.observation",
    payload,
    eventId,
    purpose,
    occurredAt: now,
    metadata: { region: "cn-east", source_version: "test" },
  });
}

function directory(name) {
  return mkdtempSync(join(tmpdir(), `ashr-event-spool-${name}-`));
}

test("event envelope is integrity sealed and rejects secret metadata", () => {
  const envelope = event();
  assert.deepEqual(validateEventEnvelope(envelope), envelope);
  assert.ok(envelope.integrity_sha256);

  const tampered = { ...envelope, payload: { content: "changed" } };
  assert.throws(() => validateEventEnvelope(tampered), EventValidationError);
  assert.throws(
    () => buildEventEnvelope({
      tenantId: "tenant_a",
      projectId: "project_a",
      runId: "run_a",
      source: "sdk",
      eventType: "trace.observation",
      payload: { content: "hello" },
      metadata: { api_key: "must-not-enter-the-spool" },
    }),
    EventValidationError,
  );
});

test("sampling is deterministic and non-droppable purposes survive zero rate", () => {
  assert.equal(deterministicSample("stable-event", 0.37), deterministicSample("stable-event", 0.37));
  assert.equal(deterministicSample("stable-event", 0), false);
  assert.equal(deterministicSample("stable-event", 1), true);

  const spool = new DurableEventSpool({ directory: directory("sampling"), samplingRate: 0 });
  assert.equal(spool.append(event({ eventId: "telemetry-dropped" })), null);
  const accepted = spool.append(event({ eventId: "audit-kept", purpose: "audit" }));
  assert.equal(accepted.event_count, 1);
  assert.deepEqual(accepted.purposes, ["audit"]);
});

test("flush reuses idempotency key across retry and resume", () => {
  const spool = new DurableEventSpool({
    directory: directory("retry"),
    retryBaseSeconds: 1,
    retryMaxSeconds: 4,
    leaseSeconds: 10,
  });
  const accepted = spool.enqueue([event({ eventId: "retry-event" })], {
    batchId: "batch_retry",
    idempotencyKey: "idem_retry",
    now,
  });
  assert.equal(accepted.batch_id, "batch_retry");
  const seen = [];

  const sender = (batch) => {
    seen.push(batch);
    if (seen.length === 1) throw new RetryableDeliveryError("token=super-secret");
  };
  assert.deepEqual(spool.flush(sender, { now, leaseOwner: "worker-a" }), {
    attempted: 1,
    delivered: 0,
    retried: 1,
    dead_lettered: 0,
    remaining: 1,
  });
  const metadata = spool.listBatches({ now: "2026-07-24T00:00:01.000Z" })[0];
  assert.equal(metadata.attempts, 1);
  assert.equal(metadata.last_failure_code, "retryable_delivery_failure");
  assert.equal(metadata.lease_expires_at, null);
  assert.doesNotMatch(readFileSync(join(spool.directory, "pending", "batch_retry.json"), "utf8"), /super-secret/);

  assert.deepEqual(spool.flush(sender, { now: "2026-07-24T00:00:01.000Z", leaseOwner: "worker-b" }), {
    attempted: 1,
    delivered: 1,
    retried: 0,
    dead_lettered: 0,
    remaining: 0,
  });
  assert.deepEqual(seen.map((batch) => batch.idempotency_key), ["idem_retry", "idem_retry"]);
  assert.deepEqual(seen.map((batch) => batch.batch_id), ["batch_retry", "batch_retry"]);
});

test("permanent failure dead-letters and redrive is explicit", () => {
  const spool = new DurableEventSpool({ directory: directory("dead"), maxAttempts: 2 });
  spool.enqueue([event({ eventId: "dead-event" })], { batchId: "batch_dead", now });
  const report = spool.flush(
    () => { throw new PermanentDeliveryError("authorization=opaque"); },
    { now },
  );
  assert.equal(report.dead_lettered, 1);
  assert.equal(report.remaining, 0);
  assert.equal(spool.listBatches({ includeDeadLetters: true })[0].status, "dead_letter");
  assert.doesNotMatch(readFileSync(join(spool.directory, "dead-letter", "batch_dead.json"), "utf8"), /opaque/);

  const redriven = spool.redrive("batch_dead", { now: "2026-07-24T00:00:05.000Z" });
  assert.equal(redriven.status, "pending");
  assert.equal(redriven.attempts, 0);
  assert.equal(
    spool.flush(() => undefined, { now: "2026-07-24T00:00:05.000Z" }).delivered,
    1,
  );
});

test("backpressure rejects by default and drop_oldest never drops audit", () => {
  const rejected = new DurableEventSpool({ directory: directory("reject"), maxBatches: 1 });
  rejected.enqueue([event({ eventId: "first" })], { now });
  assert.throws(() => rejected.enqueue([event({ eventId: "second" })], { now }), EventBackpressureError);

  const dropping = new DurableEventSpool({
    directory: directory("drop-audit"),
    maxBatches: 1,
    dropPolicy: "drop_oldest",
  });
  dropping.enqueue([event({ eventId: "audit", purpose: "audit" })], { now });
  assert.throws(() => dropping.enqueue([event({ eventId: "telemetry-2" })], { now }), EventBackpressureError);

  const telemetry = new DurableEventSpool({
    directory: directory("drop-telemetry"),
    maxBatches: 1,
    dropPolicy: "drop_oldest",
  });
  telemetry.enqueue([event({ eventId: "telemetry-1" })], { now });
  telemetry.enqueue([event({ eventId: "telemetry-2" })], { now });
  assert.equal(telemetry.listBatches().length, 1);
  assert.equal(telemetry.listBatches()[0].event_count, 1);
});

test("atomic files are valid JSON and trace sender preserves batch identity", () => {
  const spool = new DurableEventSpool({ directory: directory("trace") });
  spool.enqueue([event({ eventId: "trace-1", payload: { answer: 42 } })], {
    batchId: "batch_trace",
    now,
  });
  const pending = join(spool.directory, "pending", "batch_trace.json");
  assert.equal(JSON.parse(readFileSync(pending, "utf8")).batch_id, "batch_trace");

  const calls = [];
  const ingest = (tenantId, projectId, runId, observations, options) => {
    calls.push([tenantId, projectId, runId, observations, options.batchId, options.apiKeyId, options.idempotencyKey]);
    return { accepted: true };
  };
  const report = spool.flush(
    buildTraceIngestionSender(ingest, {
      tenantId: "tenant_a",
      projectId: "project_a",
      runId: "run_a",
      apiKeyId: "key_opaque",
    }),
    { now },
  );
  assert.equal(report.delivered, 1);
  assert.deepEqual(calls, [[
    "tenant_a",
    "project_a",
    "run_a",
    [{ answer: 42 }],
    "batch_trace",
    "key_opaque",
    "spool_batch_trace",
  ]]);
});
