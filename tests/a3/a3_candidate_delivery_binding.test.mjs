import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { test } from "node:test";
import { promisify } from "node:util";

import {
  buildA3CandidateDeliveryBinding,
  buildA3SharedCandidateIdentity,
  verifyA3CandidateDeliveryBinding,
  verifyA3SharedCandidateIdentity
} from "../../services/report/a3_candidate_delivery_binding.mjs";
import { verifyAuditBundleIndex } from "../../services/report/a3_gate_cli.mjs";

const ROOT = resolve(import.meta.dirname, "../..");
const execFileAsync = promisify(execFile);
const A3_IMPLEMENTATION_COMMIT = "a".repeat(40);
const DECISION_HEAD = "sha256:93343a7920b06dc0f232aee7b3eb82b793010ca8c2061043682b4e7ebc088797";
const GRADES_HASH = "sha256:ffeba9ab8d7a2ccfb26ca8e135448cc9a2e6c8ead5b49837f77e5e73606a5304";

test("A3 binds the rc.3 A1 run and A2 authority without changing the A2 block", async () => {
  const inputs = await rc3Inputs();
  const sharedIdentity = buildA3SharedCandidateIdentity(inputs, {
    a3GitSha: A3_IMPLEMENTATION_COMMIT,
    releaseVersion: "0.2.0-rc.3"
  });
  const identityVerification = verifyA3SharedCandidateIdentity(sharedIdentity, {
    a2SourceIdentity: inputs.a2SharedIdentity,
    a2TrustedSpine: inputs.a2TrustedSpine,
    runFixture: inputs.runFixture,
    a3GitSha: A3_IMPLEMENTATION_COMMIT,
    releaseVersion: "0.2.0-rc.3"
  });

  assert.equal(identityVerification.verified, true);
  assert.equal(sharedIdentity.binding_state, "exact");
  assert.deepEqual(sharedIdentity.blockers, []);
  assert.equal(sharedIdentity.a3.consumed_decision_hash, DECISION_HEAD);
  assert.equal(sharedIdentity.a3.consumed_grades_hash, GRADES_HASH);
  assert.equal(sharedIdentity.release_authority, false);

  const deliveryBinding = buildA3CandidateDeliveryBinding({
    ...inputs,
    a3SharedIdentity: sharedIdentity
  }, {
    a3GitSha: A3_IMPLEMENTATION_COMMIT,
    releaseVersion: "0.2.0-rc.3",
    generatedAt: "2026-07-20T14:00:00.000Z"
  });
  const bindingVerification = verifyA3CandidateDeliveryBinding(deliveryBinding, {
    ...inputs,
    a3SharedIdentity: sharedIdentity,
    a3GitSha: A3_IMPLEMENTATION_COMMIT,
    releaseVersion: "0.2.0-rc.3"
  });

  assert.equal(bindingVerification.verified, true);
  assert.equal(deliveryBinding.candidate.candidate_id, "a3-golden-agent@0.2.0-rc.3");
  assert.equal(deliveryBinding.candidate.run_id, "a3-golden-20260720-003");
  assert.equal(deliveryBinding.upstream.a2_upstream_decision, "block");
  assert.equal(deliveryBinding.upstream.a2_release_ready, false);
  assert.equal(deliveryBinding.a3.delivery_status, "blocked_by_a2");
  assert.equal(deliveryBinding.a3.production_ready, false);
  assert.equal(deliveryBinding.a3.a2_decision_recomputed, false);
});

test("A3 rejects a stale consumed Decision Ledger hash", async () => {
  const inputs = await rc3Inputs();
  const sharedIdentity = buildA3SharedCandidateIdentity(inputs, {
    a3GitSha: A3_IMPLEMENTATION_COMMIT,
    releaseVersion: "0.2.0-rc.3"
  });
  sharedIdentity.a3.consumed_decision_hash = `sha256:${"0".repeat(64)}`;
  const verification = verifyA3SharedCandidateIdentity(sharedIdentity, {
    a2SourceIdentity: inputs.a2SharedIdentity,
    a2TrustedSpine: inputs.a2TrustedSpine,
    runFixture: inputs.runFixture,
    a3GitSha: A3_IMPLEMENTATION_COMMIT,
    releaseVersion: "0.2.0-rc.3"
  });

  assert.equal(verification.verified, false);
  assert.ok(verification.blockers.includes("a3_consumed_decision_hash_mismatch"));
  assert.ok(verification.blockers.includes("spine_decision_hash_mismatch"));
});

test("A3 rejects a delivery binding that claims production readiness", async () => {
  const inputs = await rc3Inputs();
  const sharedIdentity = buildA3SharedCandidateIdentity(inputs, {
    a3GitSha: A3_IMPLEMENTATION_COMMIT,
    releaseVersion: "0.2.0-rc.3"
  });
  const deliveryBinding = buildA3CandidateDeliveryBinding({ ...inputs, a3SharedIdentity: sharedIdentity }, {
    a3GitSha: A3_IMPLEMENTATION_COMMIT,
    releaseVersion: "0.2.0-rc.3",
    generatedAt: "2026-07-20T14:00:00.000Z"
  });
  deliveryBinding.a3.production_ready = true;

  const verification = verifyA3CandidateDeliveryBinding(deliveryBinding, {
    ...inputs,
    a3SharedIdentity: sharedIdentity,
    a3GitSha: A3_IMPLEMENTATION_COMMIT,
    releaseVersion: "0.2.0-rc.3"
  });
  assert.equal(verification.verified, false);
  assert.ok(verification.blockers.includes("production_ready_claimed_without_acceptance"));
  assert.ok(verification.blockers.includes("delivery_binding_hash_invalid"));
});

test("A3 gate CLI seals exact rc.3 candidate identities into the Audit Bundle", async () => {
  const inputs = await rc3Inputs();
  const temp = await mkdtemp(join(ROOT, "fixtures/a3/golden-path/tmp-m40-05-binding-"));
  try {
    const sharedIdentity = buildA3SharedCandidateIdentity(inputs, {
      a3GitSha: A3_IMPLEMENTATION_COMMIT,
      releaseVersion: "0.2.0-rc.3"
    });
    const deliveryBinding = buildA3CandidateDeliveryBinding({ ...inputs, a3SharedIdentity: sharedIdentity }, {
      a3GitSha: A3_IMPLEMENTATION_COMMIT,
      releaseVersion: "0.2.0-rc.3",
      generatedAt: "2026-07-20T14:00:00.000Z"
    });
    const a3IdentityPath = join(temp, "a3-shared-identity.json");
    const deliveryBindingPath = join(temp, "delivery-binding.json");
    const gatePath = join(temp, "gate.json");
    const bundlePath = join(temp, "audit-bundle.json");
    await Promise.all([
      writeJson(a3IdentityPath, sharedIdentity),
      writeJson(deliveryBindingPath, deliveryBinding)
    ]);

    const base = resolve(ROOT, "fixtures/a3/golden-path/rc3");
    const completed = await execFileAsync(process.execPath, [
      resolve(ROOT, "services/report/a3_gate_cli.mjs"),
      "--runs", join(base, "a3_new_run_result.redacted.json"),
      "--grades", join(base, "a2_grade_results.json"),
      "--thresholds", resolve(ROOT, "fixtures/a3/release_gate_thresholds.json"),
      "--a2-trusted-spine", join(base, "a2_trusted_spine_handoff.snapshot.json"),
      "--a2-shared-candidate-identity", join(base, "a2_shared_candidate_identity.json"),
      "--a3-shared-candidate-identity", a3IdentityPath,
      "--candidate-delivery-binding", deliveryBindingPath,
      "--a3-implementation-commit", A3_IMPLEMENTATION_COMMIT,
      "--release-version", "0.2.0-rc.3",
      "--generated-at", "2026-07-20T14:00:00.000Z",
      "--head-sha", "1d292047e991995fdf52f0545ffff410ee19a171",
      "--output-json", gatePath,
      "--output-md", join(temp, "gate.md"),
      "--output-check", join(temp, "github-check.json"),
      "--output-pr-comment", join(temp, "pr-comment.md"),
      "--output-manifest", join(temp, "generated-manifest.json"),
      "--output-bundle", bundlePath,
      "--no-fail",
      "--json"
    ], { cwd: ROOT, maxBuffer: 4 * 1024 * 1024 });

    assert.equal(completed.stderr, "");
    const gate = await json(gatePath);
    const bundle = await json(bundlePath);
    assert.equal(gate.trusted_release_authority.integrity_verified, true);
    assert.equal(gate.trusted_release_authority.upstream_decision, "block");
    assert.equal(gate.candidate_binding_verification.verified, true);
    assert.equal(gate.candidate_binding_verification.binding_state, "exact");
    assert.equal(gate.release_gate.decision, "block_release");
    const artifactIds = bundle.bundle_artifacts.map((item) => item.id);
    assert.ok(artifactIds.includes("a2_shared_candidate_identity"));
    assert.ok(artifactIds.includes("a3_shared_candidate_identity"));
    assert.ok(artifactIds.includes("a3_candidate_delivery_binding"));
    assert.equal(bundle.release.candidate_id, "a3-golden-agent@0.2.0-rc.3");
    assert.equal(bundle.release.candidate_binding_verified, true);
    assert.equal(bundle.release.a2_grades_hash, GRADES_HASH);
    const bundleVerification = await verifyAuditBundleIndex(bundlePath, { workspaceRoot: ROOT, noFail: false });
    assert.equal(bundleVerification.status, "passed");
  } finally {
    await rm(temp, { recursive: true, force: true });
  }
});

async function rc3Inputs() {
  const base = "fixtures/a3/golden-path/rc3";
  return {
    a2SharedIdentity: await json(`${base}/a2_shared_candidate_identity.json`),
    a2TrustedSpine: await json(`${base}/a2_trusted_spine_handoff.snapshot.json`),
    runFixture: await json(`${base}/a3_new_run_result.redacted.json`)
  };
}

async function json(path) {
  return JSON.parse(await readFile(resolve(ROOT, path), "utf8"));
}

async function writeJson(path, value) {
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}
