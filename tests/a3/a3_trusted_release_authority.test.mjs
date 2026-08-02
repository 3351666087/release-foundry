import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { test } from "node:test";

import {
  evaluateA2TrustedReleaseAuthority,
  verifyA2TrustedSpine
} from "../../services/report/a3_trusted_release_authority.mjs";

const ROOT = resolve(import.meta.dirname, "../..");

test("A3 verifies every rc.3 candidate snapshot while preserving evidence_missing as a release blocker", async () => {
  const spine = await json("fixtures/a3/golden-path/rc3/a2_trusted_spine_handoff.snapshot.json");
  const integrity = verifyA2TrustedSpine(spine);
  const authority = evaluateA2TrustedReleaseAuthority(spine);

  assert.equal(integrity.integrity_verified, true);
  assert.equal(integrity.evidence_snapshots.length, 3);
  assert.deepEqual(integrity.integrity_blockers, []);
  assert.equal(authority.upstream_decision, "block");
  assert.equal(authority.release_ready, false);
  assert.equal(authority.allowed, false);
  assert.equal(authority.status, "blocked");
  assert.ok(authority.blockers.includes("evidence_incomplete"));
  assert.ok(authority.blockers.includes("a2_hard_blockers_present"));
  assert.equal(authority.decision_ledger.head_hash, "sha256:da5fde59a34df2968e28cd0b3e2a8dc495cb68b590e5c309979801d0353b7dff");
  assert.equal(authority.safety.a3_score_recomputed, false);
});

test("A3 keeps the legacy single-snapshot Trusted Spine compatible", async () => {
  const spine = await json("fixtures/a3/golden-path/rc2/a2_trusted_spine_handoff.snapshot.json");
  const authority = evaluateA2TrustedReleaseAuthority(spine);

  assert.equal(authority.integrity_verified, true);
  assert.equal(authority.upstream_decision, "block");
  assert.equal(authority.release_ready, false);
  assert.equal(authority.allowed, false);
});

test("A3 detects a changed candidate Evidence Snapshot hash", async () => {
  const spine = await json("fixtures/a3/golden-path/rc3/a2_trusted_spine_handoff.snapshot.json");
  spine.evidence_snapshots[0].snapshot_hash = `sha256:${"0".repeat(64)}`;
  const integrity = verifyA2TrustedSpine(spine);

  assert.equal(integrity.integrity_verified, false);
  assert.ok(integrity.integrity_blockers.includes("evidence_snapshot_hash_invalid:0"));
  assert.ok(integrity.integrity_blockers.includes("evidence_snapshot_mismatch:0"));
});

async function json(path) {
  return JSON.parse(await readFile(resolve(ROOT, path), "utf8"));
}
