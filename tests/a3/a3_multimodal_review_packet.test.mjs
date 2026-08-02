import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, readFile, rm, stat, writeFile } from "node:fs/promises";
import { join, relative } from "node:path";
import test from "node:test";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

import {
  buildA3MultimodalReviewAssignmentPacket,
  buildA3MultimodalReviewAssignmentProjection,
  planA3MultimodalReviewAssignmentTransition,
  verifyA3MultimodalReviewAssignmentPacket
} from "../../services/report/a3_multimodal_review_assignment.mjs";
import { buildA3MultimodalReviewQueue } from "../../services/report/a3_multimodal_review_queue.mjs";
import {
  buildAuditArchiveManifest,
  verifyAuditArchiveManifest
} from "../../services/report/a3_audit_archive.mjs";
import { buildA3ArtifactRegistry } from "../../services/report/a3_artifact_registry.mjs";
import { verifyAuditBundleIndex } from "../../services/report/a3_gate_cli.mjs";
import { buildA3MultimodalReviewPacketFromFiles } from "../../services/report/a3_multimodal_review_packet_cli.mjs";
import { summarizeMultimodalReviewQueueExport } from "../../services/report/report_builder.mjs";

const workspaceRoot = fileURLToPath(new URL("../../", import.meta.url));
const execFileAsync = promisify(execFile);
const comparisonUrl = new URL(
  "../../fixtures/a3/p3/a2_multimodal_comparison_v3_564d4b0_sample.redacted.json",
  import.meta.url
);
const tenantScope = {
  organization_id: "org-assignment",
  tenant_id: "tenant-assignment",
  workspace_id: "workspace-assignment",
  project_id: "project-assignment",
  environment_id: "staging"
};

test("multimodal assignment history packet verifies contiguous metadata-only events", async () => {
  const { queue, events } = await assignmentHistory();
  const projected = buildA3MultimodalReviewAssignmentProjection(queue, events, {
    now: "2026-07-14T12:04:01.000Z"
  });
  const packet = buildA3MultimodalReviewAssignmentPacket(projected, {
    generatedAt: "2026-07-14T12:05:00.000Z"
  });
  const verification = verifyA3MultimodalReviewAssignmentPacket(packet, {
    verifiedAt: "2026-07-14T12:05:01.000Z"
  });

  assert.equal(packet.schema_version, "a3.multimodal_review_assignment_packet.v1");
  assert.equal(packet.event_count, 3);
  assert.equal(packet.items[0].history.length, 3);
  assert.equal(packet.items[0].integrity.status, "passed");
  assert.match(packet.packet_root_hash, /^sha256:[a-f0-9]{64}$/);
  assert.equal(packet.archive_binding.audit_archive_signature_required, true);
  assert.equal(packet.archive_binding.audit_archive_signature_verified, false);
  assert.equal(packet.authority_boundary.authoritative_human_review_included, false);
  assert.equal(packet.authority_boundary.release_authority, false);
  assert.equal(verification.status, "passed");
  assert.equal(verification.root_hash.passed, true);
  assert.equal(verification.archive_signature.verified_here, false);
  assert.doesNotMatch(
    JSON.stringify(packet),
    /Bearer\s|Cookie:|RELEASEFOUNDRY_API_KEY|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|https?:\/\/|BEGIN PRIVATE KEY/i
  );
});

test("multimodal assignment packet verifier rejects tampering and self-asserted signature authority", async () => {
  const { queue, events } = await assignmentHistory();
  const packet = buildA3MultimodalReviewAssignmentPacket(queue, {
    events,
    now: "2026-07-14T12:04:01.000Z",
    generatedAt: "2026-07-14T12:05:00.000Z"
  });
  const tampered = structuredClone(packet);
  tampered.items[0].history[1].reason_code = "tampered_reason";
  tampered.archive_binding.audit_archive_signature_verified = true;

  const verification = verifyA3MultimodalReviewAssignmentPacket(tampered);
  assert.equal(verification.status, "failed");
  assert.equal(verification.root_hash.passed, false);
  assert.ok(verification.findings.some((finding) => finding.id === "packet_root_hash_mismatch"));
  assert.ok(verification.findings.some((finding) => finding.id === "event_hash_or_schema_invalid"));
  assert.ok(verification.findings.some((finding) => finding.id === "untrusted_signature_claim"));
});

test("signed Audit Archive detects assignment packet file tampering", async () => {
  const { queue, events } = await assignmentHistory();
  const packet = buildA3MultimodalReviewAssignmentPacket(queue, {
    events,
    now: "2026-07-14T12:04:01.000Z",
    generatedAt: "2026-07-14T12:05:00.000Z"
  });
  const tempDir = await mkdtemp(join(workspaceRoot, "fixtures/a3/p3/tmp-review-packet-"));
  const packetPath = join(tempDir, "multimodal-review-assignment-packet.json");
  try {
    const packetText = `${JSON.stringify(packet, null, 2)}\n`;
    await writeFile(packetPath, packetText, "utf8");
    const packetBytes = await readFile(packetPath);
    const packetStats = await stat(packetPath);
    const packetSha = createHash("sha256").update(packetBytes).digest("hex");
    const bundleIndex = {
      schema_version: "a3.audit_bundle_index.v1",
      source: "unit-test",
      bundle_id: "bundle_multimodal_review_assignment",
      bundle_root_hash: "a".repeat(64),
      bundle_artifacts: [{
        id: "multimodal_review_assignment_packet",
        path: relative(workspaceRoot, packetPath).replaceAll("\\", "/"),
        content_type: "application/json",
        required: true,
        bundle_role: "review_record",
        sha256: packetSha,
        byte_size: packetStats.size,
        redaction_status: "passed"
      }]
    };
    const archive = await buildAuditArchiveManifest(bundleIndex, {
      workspaceRoot,
      generatedAt: "2026-07-14T12:06:00.000Z",
      source: "unit-test"
    });
    const beforeTamper = await verifyAuditArchiveManifest(archive, {
      workspaceRoot,
      generatedAt: "2026-07-14T12:06:01.000Z"
    });

    assert.equal(archive.signature.algorithm, "ed25519");
    assert.equal(archive.signature.signer.identity_binding, "self_signed_local_key_not_sso_bound");
    assert.ok(archive.archive_entries.some((entry) => (
      entry.id === "multimodal_review_assignment_packet" && entry.archive_role === "review_record"
    )));
    assert.equal(beforeTamper.status, "passed");
    assert.equal(beforeTamper.signature.passed, true);

    await writeFile(packetPath, packetText.replace("manual_review_claim", "tampered_review_claim"), "utf8");
    const afterTamper = await verifyAuditArchiveManifest(archive, {
      workspaceRoot,
      generatedAt: "2026-07-14T12:06:02.000Z",
      noFail: true
    });
    assert.equal(afterTamper.status, "failed");
    assert.equal(afterTamper.signature.passed, true);
    assert.ok(afterTamper.findings.some((finding) => finding.id === "entry_hash_mismatch"));
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test("Gate CLI admits only a verified assignment packet as a signed-bundle review record", async () => {
  const { queue, events } = await assignmentHistory();
  const packet = buildA3MultimodalReviewAssignmentPacket(queue, {
    events,
    now: "2026-07-14T12:04:01.000Z",
    generatedAt: "2026-07-14T12:05:00.000Z"
  });
  const tempDir = await mkdtemp(join(workspaceRoot, "fixtures/a3/p3/tmp-gate-review-packet-"));
  const packetPath = join(tempDir, "multimodal-review-assignment-packet.json");
  const bundlePath = join(tempDir, "audit-bundle-index.json");
  try {
    await writeFile(packetPath, `${JSON.stringify(packet, null, 2)}\n`, "utf8");
    const result = await execFileAsync(process.execPath, [
      "services/report/a3_gate_cli.mjs",
      "--runs", "fixtures/a3/mock_run_results.json",
      "--grades", "fixtures/a3/mock_grade_results.json",
      "--generated-at", "2026-07-14T12:07:00.000Z",
      "--multimodal-review-packet", packetPath,
      "--output-bundle", bundlePath,
      "--no-fail",
      "--json"
    ], {
      cwd: workspaceRoot,
      maxBuffer: 5 * 1024 * 1024
    });
    const bundle = JSON.parse(await readFile(bundlePath, "utf8"));
    const artifact = bundle.bundle_artifacts.find((item) => item.id === "multimodal_review_assignment_packet");

    assert.equal(result.stderr, "");
    assert.ok(artifact);
    assert.equal(artifact.bundle_role, "review_record");
    assert.equal(artifact.origin, "a3_review_assignment_evidence");
    assert.match(artifact.sha256, /^[a-f0-9]{64}$/);
    assert.equal(artifact.required, true);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test("reports and Artifact Registry expose packet integrity without claiming archive signature", async () => {
  const { queue, events } = await assignmentHistory();
  const projected = buildA3MultimodalReviewAssignmentProjection(queue, events, {
    now: "2026-07-14T12:04:01.000Z"
  });
  const packet = buildA3MultimodalReviewAssignmentPacket(projected, {
    generatedAt: "2026-07-14T12:05:00.000Z"
  });
  const report = summarizeMultimodalReviewQueueExport({ ...projected, review_packet: packet });
  const registry = buildA3ArtifactRegistry({
    source: "p3-media",
    multimodalReviewAssignmentPacket: packet
  });
  const entry = registry.entries.find((item) => item.artifact_type === "multimodal_review_assignment_packet");
  const preset = registry.packet_presets.find((item) => item.preset_id === "multimodal_review_packet");

  assert.equal(report.review_packet.integrity_status, "passed");
  assert.equal(report.review_packet.event_count, 3);
  assert.equal(report.review_packet.audit_archive_signature_verified, false);
  assert.equal(report.items[0].assignment_history.length, 3);
  assert.equal(entry.lifecycle_state, "generated");
  assert.equal(entry.hash_status, "content_hash_present");
  assert.equal(entry.content_hash, packet.packet_root_hash);
  assert.equal(entry.missing_controls.includes("audit_archive_signature_receipt"), true);
  assert.equal(preset.missing_artifact_types.includes("multimodal_review_assignment_packet"), false);
  assert.equal(preset.missing_artifact_types.includes("report_manifest"), true);
});

test("review packet CLI builds and independently verifies redacted history files", async () => {
  const { events } = await assignmentHistory();
  const tempDir = await mkdtemp(join(workspaceRoot, "fixtures/a3/p3/tmp-review-packet-cli-"));
  const eventPath = join(tempDir, "events.json");
  const packetPath = join(tempDir, "packet.json");
  const verificationPath = join(tempDir, "verification.json");
  const markdownPath = join(tempDir, "packet.md");
  try {
    await writeFile(eventPath, `${JSON.stringify({
      schema_version: "a3.multimodal_review_assignment_events_fixture.v1",
      source: "p3-media",
      source_commit_alias: "1553562",
      tenant_scope: tenantScope,
      observed_at: "2026-07-14T12:04:01.000Z",
      events
    }, null, 2)}\n`, "utf8");
    const build = await execFileAsync(process.execPath, [
      "services/report/a3_multimodal_review_packet_cli.mjs",
      "--comparison", fileURLToPath(comparisonUrl),
      "--events", eventPath,
      "--generated-at", "2026-07-14T12:05:00.000Z",
      "--output", packetPath,
      "--output-verification", verificationPath,
      "--output-markdown", markdownPath,
      "--json"
    ], { cwd: workspaceRoot, maxBuffer: 2 * 1024 * 1024 });
    const verify = await execFileAsync(process.execPath, [
      "services/report/a3_multimodal_review_packet_cli.mjs",
      "--verify", packetPath,
      "--verified-at", "2026-07-14T12:06:00.000Z",
      "--json"
    ], { cwd: workspaceRoot, maxBuffer: 2 * 1024 * 1024 });
    const packet = JSON.parse(await readFile(packetPath, "utf8"));
    const verification = JSON.parse(verify.stdout);
    const markdown = await readFile(markdownPath, "utf8");

    assert.equal(build.stderr, "");
    assert.equal(verify.stderr, "");
    assert.equal(packet.event_count, 3);
    assert.equal(verification.status, "passed");
    assert.match(markdown, /Assignment events: 3/);
    assert.match(markdown, /Audit Archive signature: required separately/);
    assert.doesNotMatch(markdown, /Bearer|Cookie:|RELEASEFOUNDRY_API_KEY|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/i);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test("committed review packet, bundle, and signed archive reproduce and verify", async () => {
  const comparisonPath = fileURLToPath(comparisonUrl);
  const eventsPath = fileURLToPath(new URL(
    "../../fixtures/a3/p3/a3_multimodal_review_assignment_events.redacted.json",
    import.meta.url
  ));
  const packetPath = fileURLToPath(new URL(
    "../../fixtures/a3/p3/a3_multimodal_review_assignment_packet.redacted.json",
    import.meta.url
  ));
  const packetVerificationPath = fileURLToPath(new URL(
    "../../fixtures/a3/p3/a3_multimodal_review_assignment_packet_verification.redacted.json",
    import.meta.url
  ));
  const bundlePath = fileURLToPath(new URL(
    "../../fixtures/a3/p3/a3_multimodal_review_assignment_bundle.redacted.json",
    import.meta.url
  ));
  const archivePath = fileURLToPath(new URL(
    "../../fixtures/a3/p3/a3_multimodal_review_assignment_archive.redacted.json",
    import.meta.url
  ));
  const rebuilt = await buildA3MultimodalReviewPacketFromFiles({
    comparison: comparisonPath,
    events: eventsPath,
    generatedAt: "2026-07-14T12:05:00.000Z",
    verifiedAt: "2026-07-14T12:05:01.000Z"
  });
  const committedPacket = JSON.parse(await readFile(packetPath, "utf8"));
  const committedPacketVerification = JSON.parse(await readFile(packetVerificationPath, "utf8"));
  const bundleVerification = await verifyAuditBundleIndex(bundlePath, {
    workspaceRoot,
    generatedAt: "2026-07-14T12:09:01.000Z"
  });
  const archiveVerification = await verifyAuditArchiveManifest(archivePath, {
    workspaceRoot,
    generatedAt: "2026-07-14T12:09:02.000Z"
  });

  assert.deepEqual(committedPacket, rebuilt.packet);
  assert.deepEqual(committedPacketVerification, rebuilt.verification);
  assert.equal(bundleVerification.status, "passed");
  assert.ok(bundleVerification.artifacts.results.some((item) => (
    item.id === "multimodal_review_assignment_packet" && item.status === "passed"
  )));
  assert.equal(archiveVerification.status, "passed");
  assert.equal(archiveVerification.signature.passed, true);
  assert.equal(archiveVerification.signature.identity_binding, "self_signed_local_key_not_sso_bound");
  assert.ok(archiveVerification.entries.results.some((item) => (
    item.id === "multimodal_review_assignment_packet" && item.status === "passed"
  )));
  const serialized = (await Promise.all(
    [eventsPath, packetPath, bundlePath, archivePath].map((path) => readFile(path, "utf8"))
  )).join("\n");
  assert.doesNotMatch(serialized, /Bearer|Cookie:|RELEASEFOUNDRY_API_KEY|BEGIN PRIVATE KEY/i);
});

async function assignmentHistory() {
  const comparison = JSON.parse(await readFile(comparisonUrl, "utf8"));
  const queue = buildA3MultimodalReviewQueue(comparison, {
    source: "p3-media",
    tenantScope,
    sourceCommitAlias: "1553562"
  });
  const queueId = queue.items[0].queue_id;
  const events = [];
  const claim = transition(queue, events, queueId, {
    action: "claim",
    expected_version: 0,
    lease_seconds: 300
  }, "reviewer_hash_alpha", "reviewer", "2026-07-14T12:00:00.000Z");
  events.push(claim.event);
  const transfer = transition(queue, events, queueId, {
    action: "transfer",
    expected_version: 1,
    target_reviewer_hash: "reviewer_hash_beta",
    reason_code: "specialist_handoff"
  }, "reviewer_hash_alpha", "reviewer", "2026-07-14T12:02:00.000Z");
  events.push(transfer.event);
  const release = transition(queue, events, queueId, {
    action: "release",
    expected_version: 2,
    reason_code: "review_work_complete"
  }, "reviewer_hash_beta", "reviewer", "2026-07-14T12:04:00.000Z");
  events.push(release.event);
  return { queue, events };
}

function transition(queue, events, queueId, input, actorHash, actorRole, now) {
  const result = planA3MultimodalReviewAssignmentTransition(queue, events, input, {
    queueId,
    source: "p3-media",
    tenantScope,
    actorHash,
    actorRole,
    now
  });
  assert.equal(result.valid, true);
  return result;
}
