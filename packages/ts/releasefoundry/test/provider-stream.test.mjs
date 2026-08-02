import assert from "node:assert/strict";
import test from "node:test";

import { ProviderStreamIntegrityError, ProviderStreamLedger } from "../dist/index.js";

function completeStream() {
  const ledger = new ProviderStreamLedger();
  ledger.observe(0, "text_delta", "hello");
  ledger.observe(1, "tool_delta", { name: "lookup", index: 0 });
  ledger.observe(2, "completed", { finish_reason: "tool_calls" }, true);
  return ledger;
}

test("stream enforces sequence, digest identity, and terminal frame", () => {
  const ledger = new ProviderStreamLedger();
  const first = ledger.observe(0, "text_delta", "hello");
  assert.deepEqual(ledger.observe(0, "text_delta", "hello"), first);
  assert.throws(() => ledger.observe(0, "text_delta", "different"), ProviderStreamIntegrityError);
  assert.throws(() => ledger.observe(2, "text_delta", "late"), ProviderStreamIntegrityError);
  assert.throws(() => ledger.finalize(), /missing a terminal/);
  ledger.observe(1, "completed", { finish_reason: "stop" }, true);
  assert.equal(ledger.finalize().terminal_observed, true);
  assert.throws(() => ledger.observe(2, "text_delta", "impossible"), /terminal/);
});

test("stream snapshot is byte-semantics compatible and fails closed on tampering", () => {
  const snapshot = completeStream().finalize();
  assert.deepEqual(new ProviderStreamLedger(snapshot).finalize(), snapshot);
  const tampered = structuredClone(snapshot);
  tampered.frames[1].content_digest = "f".repeat(64);
  assert.throws(() => new ProviderStreamLedger(tampered), /digest chain/);
});

test("stream rejects non-canonical SHA-256 encodings", () => {
  const invalidDigests = [
    "A".repeat(64),
    "g".repeat(64),
    "0".repeat(63),
    "0".repeat(65),
    `${"0".repeat(63)} `,
    "０".repeat(64),
  ];
  for (const invalidDigest of invalidDigests) {
    const ledger = new ProviderStreamLedger();
    ledger.observe(0, "delta", "hello");
    ledger.observe(1, "done", "", true);
    const snapshot = ledger.finalize();
    snapshot.frames[0].content_digest = invalidDigest;
    assert.throws(() => new ProviderStreamLedger(snapshot), /malformed/);
  }
});

test("optional journal binding is strict, digest-bound, and content-free", () => {
  const ledger = new ProviderStreamLedger(undefined, { entry_id: "pjr_round58", fencing_token: 7 });
  ledger.observe(0, "audio_delta", "private audio payload");
  ledger.observe(1, "completed", { finish_reason: "stop" }, true);
  const snapshot = ledger.finalize();
  assert.equal(snapshot.entry_id, "pjr_round58");
  assert.equal(snapshot.fencing_token, 7);
  assert.ok(snapshot.frames.every((frame) => frame.entry_id === "pjr_round58" && frame.fencing_token === 7));
  assert.ok(!JSON.stringify(snapshot).includes("private audio payload"));
  assert.deepEqual(
    new ProviderStreamLedger(snapshot, { entry_id: "pjr_round58", fencing_token: 7 }).finalize(),
    snapshot,
  );

  const topLevelTamper = structuredClone(snapshot);
  topLevelTamper.fencing_token = 8;
  assert.throws(() => new ProviderStreamLedger(topLevelTamper), ProviderStreamIntegrityError);
  const frameTamper = structuredClone(snapshot);
  frameTamper.frames[0].entry_id = "pjr_other";
  assert.throws(() => new ProviderStreamLedger(frameTamper), ProviderStreamIntegrityError);
  const missingField = structuredClone(snapshot);
  delete missingField.frames[0].fencing_token;
  assert.throws(() => new ProviderStreamLedger(missingField), ProviderStreamIntegrityError);
  assert.throws(
    () => new ProviderStreamLedger(snapshot, { entry_id: "pjr_round58", fencing_token: 8 }),
    /conflicts/,
  );
  assert.throws(
    () => new ProviderStreamLedger(undefined, { entry_id: "pjr_round58" }),
    /appear together/,
  );
});
