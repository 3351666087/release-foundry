import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

import {
  buildAuditArchiveManifest,
  renderArchiveVerificationMarkdown,
  verifyAuditArchiveManifest
} from "../../services/report/a3_audit_archive.mjs";

const execFileAsync = promisify(execFile);

function fixturePath(path) {
  return fileURLToPath(new URL(path, import.meta.url));
}

test("A3 audit archive manifest seals bundle index and entries with signature metadata", async () => {
  const manifest = await buildAuditArchiveManifest(
    fixturePath("../../fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json"),
    {
      workspaceRoot: fixturePath("../../"),
      generatedAt: "2026-07-08T00:00:00.000Z",
      source: "unit-test"
    }
  );

  assert.equal(manifest.schema_version, "a3.audit_archive_manifest.v1");
  assert.match(manifest.archive_root_hash, /^[a-f0-9]{64}$/);
  assert.equal(manifest.immutable_policy.overwrite_allowed, false);
  assert.equal(manifest.immutable_policy.append_only_after_seal, true);
  assert.equal(manifest.immutable_policy.private_key_persisted, false);
  assert.equal(manifest.verification.verifies_archive_signature, true);
  assert.equal(manifest.safety.raw_private_key_stored, false);
  assert.ok(manifest.archive_entries.some((entry) => entry.id === "audit_bundle_index"));
  assert.ok(manifest.archive_entries.some((entry) => entry.id === "generated_artifact_manifest"));
  assert.ok(manifest.archive_entries.some((entry) => entry.id === "json_report"));
  assert.ok(manifest.archive_entries.every((entry) => !entry.path.includes("Users/")));
  assert.ok(manifest.archive_entries.every((entry) => !/^[A-Za-z]:\//.test(entry.path)));
  assert.equal(manifest.signature.algorithm, "ed25519");
  assert.equal(manifest.signature.signer.identity_binding, "self_signed_local_key_not_sso_bound");
  assert.match(manifest.signature.signature_base64, /^[A-Za-z0-9+/=]+$/);
  assert.match(manifest.signature.signer.public_key_pem, /BEGIN PUBLIC KEY/);

  const serialized = JSON.stringify(manifest);
  assert.doesNotMatch(serialized, /BEGIN PRIVATE KEY/);
  assert.doesNotMatch(serialized, /Bearer [A-Za-z0-9]/);
  assert.doesNotMatch(serialized, /Cookie:/);
});

test("A3 audit archive verifier passes signed archive manifest and renders markdown", async () => {
  const manifest = await buildAuditArchiveManifest(
    fixturePath("../../fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json"),
    {
      workspaceRoot: fixturePath("../../"),
      generatedAt: "2026-07-08T00:00:00.000Z",
      source: "unit-test"
    }
  );
  const verification = await verifyAuditArchiveManifest(manifest, {
    workspaceRoot: fixturePath("../../"),
    generatedAt: "2026-07-08T00:00:00.000Z"
  });
  const markdown = renderArchiveVerificationMarkdown(verification);

  assert.equal(verification.schema_version, "a3.audit_archive_verification.v1");
  assert.equal(verification.status, "passed");
  assert.equal(verification.root_hash.passed, true);
  assert.equal(verification.signature.passed, true);
  assert.equal(verification.entries.failed, 0);
  assert.equal(verification.entries.passed, verification.entries.total);
  assert.match(markdown, /# ReleaseFoundry Audit Archive Verification/);
  assert.match(markdown, /Signature: passed/);
});

test("A3 audit archive verifier rejects tampered manifest evidence", async () => {
  const manifest = await buildAuditArchiveManifest(
    fixturePath("../../fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json"),
    {
      workspaceRoot: fixturePath("../../"),
      generatedAt: "2026-07-08T00:00:00.000Z",
      source: "unit-test"
    }
  );
  const tampered = {
    ...manifest,
    archive_entries: manifest.archive_entries.map((entry, index) => (
      index === 0 ? { ...entry, sha256: "0".repeat(64) } : entry
    ))
  };

  const verification = await verifyAuditArchiveManifest(tampered, {
    workspaceRoot: fixturePath("../../"),
    generatedAt: "2026-07-08T00:00:00.000Z"
  });

  assert.equal(verification.status, "failed");
  assert.equal(verification.root_hash.passed, false);
  assert.equal(verification.signature.passed, false);
  assert.ok(verification.findings.some((finding) => finding.id === "archive_root_hash_mismatch"));
  assert.ok(verification.findings.some((finding) => finding.id === "archive_signature_invalid"));
  assert.ok(verification.findings.some((finding) => finding.id === "entry_hash_mismatch"));
});

test("A3 audit archive CLI writes and verifies redacted manifest evidence", async () => {
  const tempDir = await mkdtemp(join(fixturePath("../../fixtures/a3/p3/"), "tmp-audit-archive-"));
  const manifestPath = join(tempDir, "audit-archive-manifest.json");
  try {
    const command = fixturePath("../../services/report/a3_audit_archive.mjs");
    const buildResult = await execFileAsync(process.execPath, [
      command,
      "--index", "fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json",
      "--output", manifestPath,
      "--generated-at", "2026-07-08T00:00:00.000Z",
      "--source", "cli-test",
      "--json"
    ], {
      cwd: fixturePath("../../"),
      maxBuffer: 1024 * 1024
    });
    const verifyResult = await execFileAsync(process.execPath, [
      command,
      "--verify", manifestPath,
      "--generated-at", "2026-07-08T00:00:00.000Z",
      "--json"
    ], {
      cwd: fixturePath("../../"),
      maxBuffer: 1024 * 1024
    });

    assert.equal(buildResult.stderr, "");
    assert.equal(verifyResult.stderr, "");
    const stdoutManifest = JSON.parse(buildResult.stdout);
    const fileManifest = JSON.parse(await readFile(manifestPath, "utf8"));
    const verification = JSON.parse(verifyResult.stdout);
    assert.equal(stdoutManifest.archive_root_hash, fileManifest.archive_root_hash);
    assert.equal(verification.status, "passed");
    assert.equal(verification.signature.passed, true);
    assert.ok(fileManifest.archive_entries.every((entry) => !entry.path.includes(tempDir)));
    assert.ok(fileManifest.archive_entries.every((entry) => !entry.path.includes("Users/")));
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test("A3 audit archive verifier detects missing archive entry files", async () => {
  const tempDir = await mkdtemp(join(fixturePath("../../fixtures/a3/p3/"), "tmp-audit-archive-missing-"));
  const manifestPath = join(tempDir, "audit-archive-manifest.json");
  try {
    const manifest = await buildAuditArchiveManifest(
      fixturePath("../../fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json"),
      {
        workspaceRoot: fixturePath("../../"),
        generatedAt: "2026-07-08T00:00:00.000Z",
        source: "unit-test"
      }
    );
    const missingManifest = {
      ...manifest,
      archive_entries: manifest.archive_entries.map((entry, index) => (
        index === 0 ? { ...entry, path: "fixtures/a3/p3/missing-audit-archive-entry.json" } : entry
      ))
    };
    await writeFile(manifestPath, `${JSON.stringify(missingManifest, null, 2)}\n`, "utf8");

    const verification = await verifyAuditArchiveManifest(manifestPath, {
      workspaceRoot: fixturePath("../../"),
      generatedAt: "2026-07-08T00:00:00.000Z",
      noFail: true
    });

    assert.equal(verification.status, "failed");
    assert.ok(verification.findings.some((finding) => finding.id === "entry_missing"));
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});
