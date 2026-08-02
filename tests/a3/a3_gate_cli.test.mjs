import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

import {
  buildAuditBundleIndex,
  buildGeneratedArtifactManifest,
  buildGateCliPayload,
  renderBundleVerificationMarkdown,
  renderGateCliMarkdown,
  verifyAuditBundleIndex,
  validateApprovalRecord,
  validateWaiverRequest
} from "../../services/report/a3_gate_cli.mjs";

const execFileAsync = promisify(execFile);

function fixturePath(path) {
  return fileURLToPath(new URL(path, import.meta.url));
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

test("A3 gate CLI builder emits PR gate payload with hashed audit inputs", async () => {
  const payload = await buildGateCliPayload({
    runs: fixturePath("../../fixtures/a3/mock_run_results.json"),
    grades: fixturePath("../../fixtures/a3/mock_grade_results.json"),
    coverage: fixturePath("../../fixtures/a2/results/a2_g3_coverage_report.json"),
    thresholds: fixturePath("../../fixtures/a3/release_gate_thresholds.json"),
    releaseVersion: "refund-agent-cli-test",
    environment: "staging",
    owner: "A3 owner",
    generatedAt: "2026-07-07T00:00:00.000Z",
    source: "unit-test"
  });

  assert.equal(payload.schema_version, "a3.gate_cli.v1");
  assert.equal(payload.command_shape, "releasefoundry gate --json");
  assert.equal(payload.release_gate.decision, "block_release");
  assert.equal(payload.release_workflow.github_check.conclusion, "failure");
  assert.equal(payload.release_workflow.github_check.blocks_merge, true);
  assert.equal(payload.release_gate.thresholds.pass_rate_min, 95);
  assert.equal(payload.release_gate.thresholds.trace_completeness_min, 90);
  assert.equal(payload.exit_code_hint, 1);
  assert.equal(payload.process_exit_code, 1);
  assert.ok(payload.audit_manifest.artifacts.length >= 4);
  assert.ok(payload.audit_manifest.artifacts.every((artifact) => /^[a-f0-9]{64}$/.test(artifact.sha256)));
  assert.ok(payload.audit_manifest.artifacts.every((artifact) => artifact.path.startsWith("fixtures/")));
  assert.ok(payload.audit_manifest.redaction_policy.includes("No API keys"));

  const markdown = renderGateCliMarkdown(payload);
  assert.match(markdown, /# ReleaseFoundry Gate CLI Report/);
  assert.match(markdown, /Check conclusion: failure/);
  assert.match(markdown, /## Audit Manifest/);
  assert.match(markdown, /## Waiver Review/);
  assert.match(markdown, /## Approval Review/);
  assert.match(markdown, /## PR Comment/);
});

test("A3 gate CLI command writes JSON and uses strict exit for blocked release", async () => {
  const command = fixturePath("../../services/report/a3_gate_cli.mjs");
  const args = [
    command,
    "--runs", fixturePath("../../fixtures/a3/mock_run_results.json"),
    "--grades", fixturePath("../../fixtures/a3/mock_grade_results.json"),
    "--coverage", fixturePath("../../fixtures/a2/results/a2_g3_coverage_report.json"),
    "--thresholds", fixturePath("../../fixtures/a3/release_gate_thresholds.json"),
    "--release-version", "refund-agent-cli-command",
    "--source", "cli-test",
    "--strict-exit",
    "--json"
  ];

  let completed;
  try {
    completed = await execFileAsync(process.execPath, args, {
      maxBuffer: 1024 * 1024
    });
  } catch (error) {
    completed = error;
  }

  assert.equal(completed.code, 1);
  assert.equal(completed.stderr, "");
  const payload = JSON.parse(completed.stdout);
  assert.equal(payload.release_workflow.github_check.name, "ReleaseFoundry Release Gate");
  assert.equal(payload.release_workflow.release_version, "refund-agent-cli-command");
  assert.equal(payload.release_gate.pr_gate.blocks_merge, true);
  assert.equal(payload.exit_mode, "strict-exit");
  assert.equal(payload.process_exit_code, 1);
  assert.ok(payload.audit_manifest.artifacts.some((artifact) => artifact.id === "thresholds"));
  assert.ok(payload.audit_manifest.artifacts.every((artifact) => !artifact.path.includes("Users/")));
});

test("A3 gate CLI no-fail mode writes blocked evidence without failing local generation", async () => {
  const command = fixturePath("../../services/report/a3_gate_cli.mjs");
  const args = [
    command,
    "--runs", fixturePath("../../fixtures/a3/mock_run_results.json"),
    "--grades", fixturePath("../../fixtures/a3/mock_grade_results.json"),
    "--coverage", fixturePath("../../fixtures/a2/results/a2_g3_coverage_report.json"),
    "--thresholds", fixturePath("../../fixtures/a3/release_gate_thresholds.json"),
    "--release-version", "refund-agent-cli-no-fail",
    "--source", "cli-test",
    "--no-fail",
    "--json"
  ];

  const completed = await execFileAsync(process.execPath, args, {
    maxBuffer: 1024 * 1024
  });

  assert.equal(completed.stderr, "");
  const payload = JSON.parse(completed.stdout);
  assert.equal(payload.release_gate.decision, "block_release");
  assert.equal(payload.exit_code_hint, 1);
  assert.equal(payload.process_exit_code, 0);
  assert.equal(payload.exit_mode, "no-fail");
});

test("A3 gate CLI validates file-backed exceptional waiver evidence", async () => {
  const payload = await buildGateCliPayload({
    runs: fixturePath("../../fixtures/a3/mock_run_results.json"),
    grades: fixturePath("../../fixtures/a3/mock_grade_results.json"),
    coverage: fixturePath("../../fixtures/a2/results/a2_g3_coverage_report.json"),
    thresholds: fixturePath("../../fixtures/a3/release_gate_thresholds.json"),
    waiver: fixturePath("../../fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json"),
    releaseVersion: "local-mock-commercial-gate",
    environment: "staging",
    owner: "A3 owner",
    generatedAt: "2026-07-07T00:00:00.000Z",
    headSha: "local-demo-head-sha",
    source: "unit-test"
  });

  assert.equal(payload.release_gate.decision, "block_release");
  assert.equal(payload.waiver_review.schema_version, "a3.waiver_review.v1");
  assert.equal(payload.waiver_review.status, "valid_exceptional_waiver");
  assert.equal(payload.waiver_review.accepted, true);
  assert.equal(payload.waiver_review.automatic_unblock, false);
  assert.equal(payload.waiver_review.waiver.missing_approvers.length, 0);
  assert.equal(payload.waiver_review.waiver.missing_failed_checks.length, 0);
  assert.equal(payload.waiver_review.waiver.reviewed_artifact_count, 1);
  assert.equal(payload.process_exit_code, 1);
  assert.ok(payload.audit_manifest.artifacts.some((artifact) => artifact.id === "waiver"));
});

test("A3 waiver validation rejects expired or incomplete waiver evidence", async () => {
  const payload = await buildGateCliPayload({
    runs: fixturePath("../../fixtures/a3/mock_run_results.json"),
    grades: fixturePath("../../fixtures/a3/mock_grade_results.json"),
    coverage: fixturePath("../../fixtures/a2/results/a2_g3_coverage_report.json"),
    thresholds: fixturePath("../../fixtures/a3/release_gate_thresholds.json"),
    releaseVersion: "local-mock-commercial-gate",
    environment: "staging",
    generatedAt: "2026-07-07T00:00:00.000Z",
    headSha: "local-demo-head-sha",
    source: "unit-test"
  });
  const waiver = JSON.parse(await readFile(
    fixturePath("../../fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json"),
    "utf8"
  ));
  const review = validateWaiverRequest({
    ...waiver,
    expiry_date: "2026-07-06T00:00:00.000Z",
    approved_by: waiver.approved_by.slice(0, 1)
  }, payload.release_gate, payload.release_workflow, payload.summary, {
    generatedAt: "2026-07-07T00:00:00.000Z",
    releaseVersion: "local-mock-commercial-gate",
    environment: "staging",
    headSha: "local-demo-head-sha"
  });

  assert.equal(review.status, "invalid_waiver");
  assert.equal(review.accepted, false);
  assert.ok(review.findings.some((finding) => finding.id === "expiry_date_expired"));
  assert.ok(review.findings.some((finding) => finding.id === "missing_required_approvers"));
});

test("A3 waiver review fixture preserves accepted exceptional waiver shape", async () => {
  const review = JSON.parse(await readFile(
    fixturePath("../../fixtures/a3/p3/a3_waiver_review_blocked_exception.redacted.json"),
    "utf8"
  ));

  assert.equal(review.schema_version, "a3.waiver_review.v1");
  assert.equal(review.status, "valid_exceptional_waiver");
  assert.equal(review.accepted, true);
  assert.equal(review.automatic_unblock, false);
  assert.equal(review.waiver.missing_approvers.length, 0);
  assert.equal(review.waiver.missing_failed_checks.length, 0);
});

test("A3 gate CLI validates file-backed exception approval evidence", async () => {
  const payload = await buildGateCliPayload({
    runs: fixturePath("../../fixtures/a3/mock_run_results.json"),
    grades: fixturePath("../../fixtures/a3/mock_grade_results.json"),
    coverage: fixturePath("../../fixtures/a2/results/a2_g3_coverage_report.json"),
    thresholds: fixturePath("../../fixtures/a3/release_gate_thresholds.json"),
    waiver: fixturePath("../../fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json"),
    approval: fixturePath("../../fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json"),
    releaseVersion: "local-mock-commercial-gate",
    environment: "staging",
    owner: "A3 owner",
    generatedAt: "2026-07-07T00:00:00.000Z",
    headSha: "local-demo-head-sha",
    source: "unit-test"
  });

  assert.equal(payload.release_gate.decision, "block_release");
  assert.equal(payload.approval_review.schema_version, "a3.approval_review.v1");
  assert.equal(payload.approval_review.status, "valid_exception_approval");
  assert.equal(payload.approval_review.accepted, true);
  assert.equal(payload.approval_review.automatic_unblock, false);
  assert.equal(payload.approval_review.approval.decision, "approve_exception");
  assert.equal(payload.approval_review.approval.missing_required_signer_roles.length, 0);
  assert.equal(payload.approval_review.approval.reviewed_artifact_count, 2);
  assert.equal(payload.process_exit_code, 1);
  assert.ok(payload.audit_manifest.artifacts.some((artifact) => artifact.id === "approval"));
});

test("A3 approval validation rejects missing signer roles and self-approval", async () => {
  const payload = await buildGateCliPayload({
    runs: fixturePath("../../fixtures/a3/mock_run_results.json"),
    grades: fixturePath("../../fixtures/a3/mock_grade_results.json"),
    coverage: fixturePath("../../fixtures/a2/results/a2_g3_coverage_report.json"),
    thresholds: fixturePath("../../fixtures/a3/release_gate_thresholds.json"),
    waiver: fixturePath("../../fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json"),
    releaseVersion: "local-mock-commercial-gate",
    environment: "staging",
    generatedAt: "2026-07-07T00:00:00.000Z",
    headSha: "local-demo-head-sha",
    source: "unit-test"
  });
  const waiver = JSON.parse(await readFile(
    fixturePath("../../fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json"),
    "utf8"
  ));
  const approval = JSON.parse(await readFile(
    fixturePath("../../fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json"),
    "utf8"
  ));
  const review = validateApprovalRecord({
    ...approval,
    decision: "approve_release",
    co_signers: [],
    separation_of_duties: {
      release_author: "Release owner",
      release_author_is_signer: true
    }
  }, payload.release_gate, payload.release_workflow, payload.summary, {
    waiver,
    generatedAt: "2026-07-07T00:00:00.000Z",
    releaseVersion: "local-mock-commercial-gate",
    environment: "staging",
    headSha: "local-demo-head-sha"
  });

  assert.equal(review.status, "invalid_approval");
  assert.equal(review.accepted, false);
  assert.ok(review.findings.some((finding) => finding.id === "decision_too_permissive"));
  assert.ok(review.findings.some((finding) => finding.id === "missing_required_signer_roles"));
  assert.ok(review.findings.some((finding) => finding.id === "separation_of_duties_failed"));
});

test("A3 approval review fixture preserves accepted exception approval shape", async () => {
  const review = JSON.parse(await readFile(
    fixturePath("../../fixtures/a3/p3/a3_approval_review_blocked_exception.redacted.json"),
    "utf8"
  ));

  assert.equal(review.schema_version, "a3.approval_review.v1");
  assert.equal(review.status, "valid_exception_approval");
  assert.equal(review.accepted, true);
  assert.equal(review.automatic_unblock, false);
  assert.equal(review.approval.missing_required_signer_roles.length, 0);
  assert.equal(review.approval.reviewed_artifact_count, 2);
});

test("A3 gate CLI writes CI output files and GitHub check annotations", async () => {
  const tempDir = await mkdtemp(join(tmpdir(), "a3-gate-cli-"));
  const paths = {
    json: join(tempDir, "gate.json"),
    markdown: join(tempDir, "gate.md"),
    check: join(tempDir, "check.json"),
    comment: join(tempDir, "pr-comment.md")
  };
  try {
    const command = fixturePath("../../services/report/a3_gate_cli.mjs");
    const completed = await execFileAsync(process.execPath, [
      command,
      "--runs", "fixtures/a3/mock_run_results.json",
      "--grades", "fixtures/a3/mock_grade_results.json",
      "--coverage", "fixtures/a2/results/a2_g3_coverage_report.json",
      "--thresholds", "fixtures/a3/release_gate_thresholds.json",
      "--release-version", "refund-agent-output-files",
      "--source", "cli-output-test",
      "--head-sha", "abc123",
      "--details-url", "https://example.invalid/a3-gate",
      "--annotation-path", "docs/a3/p3_gate_cli_growth_2026_07_07.md",
      "--output-json", paths.json,
      "--output-md", paths.markdown,
      "--output-check", paths.check,
      "--output-pr-comment", paths.comment,
      "--no-fail",
      "--json"
    ], {
      cwd: fixturePath("../../"),
      maxBuffer: 1024 * 1024
    });

    assert.equal(completed.stderr, "");
    const json = JSON.parse(await readFile(paths.json, "utf8"));
    const check = JSON.parse(await readFile(paths.check, "utf8"));
    const markdown = await readFile(paths.markdown, "utf8");
    const comment = await readFile(paths.comment, "utf8");

    assert.equal(json.process_exit_code, 0);
    assert.equal(check.name, "ReleaseFoundry Release Gate");
    assert.equal(check.head_sha, "abc123");
    assert.equal(check.conclusion, "failure");
    assert.ok(check.output.annotations.length > 0);
    assert.equal(check.output.annotations[0].path, "docs/a3/p3_gate_cli_growth_2026_07_07.md");
    assert.match(markdown, /# ReleaseFoundry Gate CLI Report/);
    assert.match(comment, /## ReleaseFoundry Release Gate/);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test("A3 gate CLI writes generated artifact manifest with output hashes", async () => {
  const tempDir = await mkdtemp(join(tmpdir(), "a3-gate-cli-manifest-"));
  const paths = {
    json: join(tempDir, "gate.json"),
    markdown: join(tempDir, "gate.md"),
    check: join(tempDir, "check.json"),
    comment: join(tempDir, "pr-comment.md"),
    manifest: join(tempDir, "generated-artifacts.json")
  };
  try {
    const command = fixturePath("../../services/report/a3_gate_cli.mjs");
    const completed = await execFileAsync(process.execPath, [
      command,
      "--runs", "fixtures/a3/mock_run_results.json",
      "--grades", "fixtures/a3/mock_grade_results.json",
      "--coverage", "fixtures/a2/results/a2_g3_coverage_report.json",
      "--thresholds", "fixtures/a3/release_gate_thresholds.json",
      "--release-version", "refund-agent-output-manifest",
      "--source", "cli-output-manifest-test",
      "--head-sha", "abc123",
      "--details-url", "https://example.invalid/a3-gate",
      "--output-json", paths.json,
      "--output-md", paths.markdown,
      "--output-check", paths.check,
      "--output-pr-comment", paths.comment,
      "--output-manifest", paths.manifest,
      "--no-fail",
      "--json"
    ], {
      cwd: fixturePath("../../"),
      maxBuffer: 1024 * 1024
    });

    assert.equal(completed.stderr, "");
    const manifest = JSON.parse(await readFile(paths.manifest, "utf8"));
    const artifactsById = new Map(manifest.generated_artifacts.map((artifact) => [artifact.id, artifact]));
    const artifactPaths = {
      json_report: paths.json,
      markdown_report: paths.markdown,
      github_check_run: paths.check,
      pr_comment_markdown: paths.comment
    };

    assert.equal(manifest.schema_version, "a3.generated_artifact_manifest.v1");
    assert.equal(manifest.release.decision, "block_release");
    assert.equal(manifest.release.blocks_merge, true);
    assert.equal(manifest.safety.contains_secret_values, false);
    assert.equal(manifest.safety.local_absolute_paths_allowed, false);
    assert.equal(manifest.safety.manifest_hashes_itself, false);
    assert.equal(manifest.generated_artifacts.length, 4);

    for (const [id, path] of Object.entries(artifactPaths)) {
      const bytes = await readFile(path);
      const artifact = artifactsById.get(id);
      assert.ok(artifact, `missing artifact ${id}`);
      assert.equal(artifact.sha256, sha256(bytes));
      assert.equal(artifact.byte_size, bytes.length);
      assert.equal(artifact.path.includes(tempDir), false);
      assert.equal(artifact.path.includes("Users/"), false);
      assert.match(artifact.sha256, /^[a-f0-9]{64}$/);
    }
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test("A3 generated artifact manifest builder exposes enterprise audit shape", () => {
  const manifest = buildGeneratedArtifactManifest({
    generated_at: "2026-07-07T00:00:00.000Z",
    source: "unit-test",
    command_shape: "releasefoundry gate --json",
    summary: { lastRunId: "run-1" },
    release_gate: {
      decision: "block_release",
      decision_label: "Block release",
      risk_score: 88,
      pr_gate: { blocks_merge: true }
    },
    release_workflow: {
      github_check: { conclusion: "failure" }
    },
    audit_manifest: {
      redaction_policy: "No secrets."
    }
  }, [{
    id: "json_report",
    path: "fixtures/a3/p3/report.json",
    content_type: "application/json",
    sha256: "a".repeat(64),
    byte_size: 42
  }], {
    outputManifest: "fixtures/a3/p3/manifest.json",
    workspaceRoot: fixturePath("../../")
  });

  assert.equal(manifest.schema_version, "a3.generated_artifact_manifest.v1");
  assert.equal(manifest.release.run_id, "run-1");
  assert.equal(manifest.release.risk_score, 88);
  assert.equal(manifest.generated_artifacts[0].id, "json_report");
  assert.equal(manifest.generated_artifacts[0].sha256, "a".repeat(64));
  assert.equal(manifest.manifest_self_hash, "excluded_to_avoid_self_reference");
});

test("A3 audit bundle index seals source and generated evidence with a stable root hash", async () => {
  const payload = await buildGateCliPayload({
    runs: fixturePath("../../fixtures/a3/mock_run_results.json"),
    grades: fixturePath("../../fixtures/a3/mock_grade_results.json"),
    coverage: fixturePath("../../fixtures/a2/results/a2_g3_coverage_report.json"),
    thresholds: fixturePath("../../fixtures/a3/release_gate_thresholds.json"),
    waiver: fixturePath("../../fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json"),
    approval: fixturePath("../../fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json"),
    releaseVersion: "local-mock-commercial-gate",
    environment: "staging",
    owner: "A3 owner",
    generatedAt: "2026-07-07T00:00:00.000Z",
    headSha: "local-demo-head-sha",
    source: "unit-test"
  });
  const reportPath = fixturePath("../../fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json");
  const reportBytes = await readFile(reportPath);
  const generatedArtifacts = [{
    id: "json_report",
    path: reportPath,
    content_type: "application/json",
    sha256: sha256(reportBytes),
    byte_size: reportBytes.length
  }, {
    id: "audit_bundle_index",
    path: fixturePath("../../fixtures/a3/p3/ignored-self-index.redacted.json"),
    content_type: "application/json",
    sha256: "b".repeat(64),
    byte_size: 123
  }];

  const bundle = buildAuditBundleIndex(payload, generatedArtifacts, {
    outputBundle: "fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json",
    workspaceRoot: fixturePath("../../"),
    releaseVersion: "local-mock-commercial-gate",
    environment: "staging",
    owner: "A3 owner"
  });
  const rebuilt = buildAuditBundleIndex(payload, generatedArtifacts, {
    outputBundle: "fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json",
    workspaceRoot: fixturePath("../../"),
    releaseVersion: "local-mock-commercial-gate",
    environment: "staging",
    owner: "A3 owner"
  });

  assert.equal(bundle.schema_version, "a3.audit_bundle_index.v1");
  assert.match(bundle.bundle_root_hash, /^[a-f0-9]{64}$/);
  assert.equal(bundle.bundle_root_hash, rebuilt.bundle_root_hash);
  assert.equal(bundle.release.decision, "block_release");
  assert.equal(bundle.governance.waiver_status, "valid_exceptional_waiver");
  assert.equal(bundle.governance.approval_status, "valid_exception_approval");
  assert.ok(bundle.bundle_artifacts.some((artifact) => artifact.id === "waiver"));
  assert.ok(bundle.bundle_artifacts.some((artifact) => artifact.id === "approval"));
  assert.ok(bundle.bundle_artifacts.some((artifact) => artifact.id === "json_report"));
  assert.equal(bundle.bundle_artifacts.some((artifact) => artifact.id === "audit_bundle_index"), false);
  assert.ok(bundle.bundle_artifacts.every((artifact) => !artifact.path.includes("Users/")));
  assert.ok(bundle.bundle_artifacts.every((artifact) => !artifact.path.match(/^[A-Za-z]:\//)));
  assert.deepEqual(bundle.chain_of_custody.map((event) => event.action), [
    "gate_built",
    "input_artifacts_hashed",
    "generated_artifacts_hashed",
    "waiver_reviewed",
    "approval_reviewed",
    "bundle_index_written"
  ]);
  assert.ok(bundle.chain_of_custody.every((event) => /^[a-f0-9]{64}$/.test(event.event_hash)));
});

test("A3 gate CLI writes audit bundle index with generated manifest and governance records", async () => {
  const tempDir = await mkdtemp(join(tmpdir(), "a3-gate-cli-bundle-"));
  const paths = {
    json: join(tempDir, "gate.json"),
    markdown: join(tempDir, "gate.md"),
    check: join(tempDir, "check.json"),
    comment: join(tempDir, "pr-comment.md"),
    manifest: join(tempDir, "generated-artifacts.json"),
    bundle: join(tempDir, "audit-bundle-index.json")
  };
  try {
    const command = fixturePath("../../services/report/a3_gate_cli.mjs");
    const completed = await execFileAsync(process.execPath, [
      command,
      "--runs", "fixtures/a3/mock_run_results.json",
      "--grades", "fixtures/a3/mock_grade_results.json",
      "--coverage", "fixtures/a2/results/a2_g3_coverage_report.json",
      "--thresholds", "fixtures/a3/release_gate_thresholds.json",
      "--waiver", "fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json",
      "--approval", "fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json",
      "--release-version", "local-mock-commercial-gate",
      "--environment", "staging",
      "--source", "cli-output-bundle-test",
      "--head-sha", "local-demo-head-sha",
      "--output-json", paths.json,
      "--output-md", paths.markdown,
      "--output-check", paths.check,
      "--output-pr-comment", paths.comment,
      "--output-manifest", paths.manifest,
      "--output-bundle", paths.bundle,
      "--no-fail",
      "--json"
    ], {
      cwd: fixturePath("../../"),
      maxBuffer: 1024 * 1024
    });

    assert.equal(completed.stderr, "");
    const bundle = JSON.parse(await readFile(paths.bundle, "utf8"));
    const artifactIds = new Set(bundle.bundle_artifacts.map((artifact) => artifact.id));

    assert.equal(bundle.schema_version, "a3.audit_bundle_index.v1");
    assert.equal(bundle.release.blocks_merge, true);
    assert.equal(bundle.completeness.status, "complete");
    assert.match(bundle.bundle_root_hash, /^[a-f0-9]{64}$/);
    assert.equal(artifactIds.has("runs"), true);
    assert.equal(artifactIds.has("grades"), true);
    assert.equal(artifactIds.has("waiver"), true);
    assert.equal(artifactIds.has("approval"), true);
    assert.equal(artifactIds.has("generated_artifact_manifest"), true);
    assert.equal(artifactIds.has("audit_bundle_index"), false);
    assert.ok(bundle.bundle_artifacts.every((artifact) => !artifact.path.includes(tempDir)));
    assert.ok(bundle.bundle_artifacts.every((artifact) => !artifact.path.includes("Users/")));
    assert.equal(bundle.safety.self_hash_excluded, true);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test("A3 gate CLI seals GitHub publish evidence into generated manifest and audit bundle", async () => {
  const tempDir = await mkdtemp(join(fixturePath("../../fixtures/a3/p3/"), "tmp-github-evidence-"));
  const paths = {
    json: join(tempDir, "gate.json"),
    markdown: join(tempDir, "gate.md"),
    check: join(tempDir, "check.json"),
    comment: join(tempDir, "pr-comment.md"),
    manifest: join(tempDir, "generated-artifacts.json"),
    bundle: join(tempDir, "audit-bundle-index.json")
  };
  const evidencePaths = {
    github_check_publish_receipt: fixturePath("../../fixtures/a3/p3/a3_github_check_publish_receipt_dry_run.redacted.json"),
    github_pr_comment_publish_receipt: fixturePath("../../fixtures/a3/p3/a3_github_pr_comment_publish_receipt_dry_run.redacted.json"),
    github_required_check_plan: fixturePath("../../fixtures/a3/p3/a3_github_required_check_plan.redacted.json")
  };
  try {
    const command = fixturePath("../../services/report/a3_gate_cli.mjs");
    const completed = await execFileAsync(process.execPath, [
      command,
      "--runs", "fixtures/a3/mock_run_results.json",
      "--grades", "fixtures/a3/mock_grade_results.json",
      "--coverage", "fixtures/a2/results/a2_g3_coverage_report.json",
      "--thresholds", "fixtures/a3/release_gate_thresholds.json",
      "--release-version", "local-mock-commercial-gate",
      "--environment", "staging",
      "--source", "cli-github-publish-evidence-test",
      "--head-sha", "local-demo-head-sha",
      "--output-json", paths.json,
      "--output-md", paths.markdown,
      "--output-check", paths.check,
      "--output-pr-comment", paths.comment,
      "--output-manifest", paths.manifest,
      "--output-bundle", paths.bundle,
      "--github-check-publish-receipt", "fixtures/a3/p3/a3_github_check_publish_receipt_dry_run.redacted.json",
      "--github-pr-comment-publish-receipt", "fixtures/a3/p3/a3_github_pr_comment_publish_receipt_dry_run.redacted.json",
      "--github-required-check-plan", "fixtures/a3/p3/a3_github_required_check_plan.redacted.json",
      "--no-fail",
      "--json"
    ], {
      cwd: fixturePath("../../"),
      maxBuffer: 1024 * 1024
    });

    assert.equal(completed.stderr, "");
    const manifest = JSON.parse(await readFile(paths.manifest, "utf8"));
    const bundle = JSON.parse(await readFile(paths.bundle, "utf8"));
    const manifestById = new Map(manifest.generated_artifacts.map((artifact) => [artifact.id, artifact]));
    const bundleById = new Map(bundle.bundle_artifacts.map((artifact) => [artifact.id, artifact]));

    assert.equal(manifest.generated_artifacts.length, 7);
    assert.equal(bundle.completeness.status, "complete");
    assert.match(bundle.bundle_root_hash, /^[a-f0-9]{64}$/);
    assert.deepEqual([
      bundleById.has("github_check_publish_receipt"),
      bundleById.has("github_pr_comment_publish_receipt"),
      bundleById.has("github_required_check_plan")
    ], [true, true, true]);

    for (const [id, evidencePath] of Object.entries(evidencePaths)) {
      const bytes = await readFile(evidencePath);
      const manifestArtifact = manifestById.get(id);
      const bundleArtifact = bundleById.get(id);
      assert.ok(manifestArtifact, `missing manifest artifact ${id}`);
      assert.ok(bundleArtifact, `missing bundle artifact ${id}`);
      assert.equal(manifestArtifact.origin, "external_github_publish_evidence");
      assert.equal(bundleArtifact.origin, "external_github_publish_evidence");
      assert.equal(bundleArtifact.created_by, "releasefoundry gate external GitHub publish evidence reader");
      assert.equal(manifestArtifact.sha256, sha256(bytes));
      assert.equal(bundleArtifact.sha256, sha256(bytes));
      assert.equal(manifestArtifact.byte_size, bytes.length);
      assert.equal(bundleArtifact.byte_size, bytes.length);
      assert.equal(manifestArtifact.path.startsWith("fixtures/a3/p3/"), true);
      assert.equal(bundleArtifact.path.startsWith("fixtures/a3/p3/"), true);
      assert.equal(bundleArtifact.path.includes("Users/"), false);
      assert.equal(bundleArtifact.path.match(/^[A-Za-z]:\//), null);
    }

    const verification = await verifyAuditBundleIndex(paths.bundle, {
      workspaceRoot: fixturePath("../../"),
      generatedAt: "2026-07-07T00:00:00.000Z"
    });
    assert.equal(verification.status, "passed");
    assert.equal(verification.root_hash.passed, true);
    assert.equal(verification.artifacts.failed, 0);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test("A3 gate CLI seals GitHub Actions artifact readback into the audit bundle", async () => {
  const tempDir = await mkdtemp(join(fixturePath("../../fixtures/a3/p3/"), "tmp-actions-artifact-readback-"));
  const manifestPath = join(tempDir, "generated-artifacts.json");
  const bundlePath = join(tempDir, "audit-bundle-index.json");
  const readbackPath = "fixtures/a3/golden-path/github-actions-artifact-live-readback.redacted.json";
  try {
    const completed = await execFileAsync(process.execPath, [
      fixturePath("../../services/report/a3_gate_cli.mjs"),
      "--runs", "fixtures/a3/mock_run_results.json",
      "--grades", "fixtures/a3/mock_grade_results.json",
      "--coverage", "fixtures/a2/results/a2_g3_coverage_report.json",
      "--thresholds", "fixtures/a3/release_gate_thresholds.json",
      "--release-version", "local-actions-artifact-readback",
      "--source", "cli-actions-artifact-readback-test",
      "--output-manifest", manifestPath,
      "--output-bundle", bundlePath,
      "--github-actions-artifact-readback", readbackPath,
      "--no-fail",
      "--json"
    ], {
      cwd: fixturePath("../../"),
      maxBuffer: 1024 * 1024
    });

    assert.equal(completed.stderr, "");
    const sourceBytes = await readFile(fixturePath(`../../${readbackPath}`));
    const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
    const bundle = JSON.parse(await readFile(bundlePath, "utf8"));
    const manifestArtifact = manifest.generated_artifacts.find((item) => item.id === "github_actions_artifact_readback");
    const bundleArtifact = bundle.bundle_artifacts.find((item) => item.id === "github_actions_artifact_readback");

    assert.equal(manifestArtifact.origin, "external_github_live_readback");
    assert.equal(bundleArtifact.bundle_role, "readback_record");
    assert.equal(bundleArtifact.sha256, sha256(sourceBytes));
    assert.equal(bundleArtifact.byte_size, sourceBytes.length);
    assert.ok(bundle.artifact_groups.readback_records.includes("github_actions_artifact_readback"));
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test("A3 audit bundle verifier passes committed bundle and renders markdown evidence", async () => {
  const verification = await verifyAuditBundleIndex(
    fixturePath("../../fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json"),
    {
      workspaceRoot: fixturePath("../../"),
      generatedAt: "2026-07-07T00:00:00.000Z"
    }
  );
  const markdown = renderBundleVerificationMarkdown(verification);

  assert.equal(verification.schema_version, "a3.audit_bundle_verification.v1");
  assert.equal(verification.status, "passed");
  assert.equal(verification.root_hash.passed, true);
  assert.equal(verification.artifacts.failed, 0);
  assert.equal(verification.artifacts.passed, verification.artifacts.total);
  assert.equal(verification.chain_of_custody.failed, 0);
  assert.match(verification.root_hash.actual, /^[a-f0-9]{64}$/);
  assert.match(markdown, /# ReleaseFoundry Audit Bundle Verification/);
  assert.match(markdown, /Status: passed/);
});

test("A3 audit bundle verifier rejects tampered artifact hash evidence", async () => {
  const tempDir = await mkdtemp(join(tmpdir(), "a3-bundle-verify-"));
  const tamperedPath = join(tempDir, "tampered-index.json");
  try {
    const index = JSON.parse(await readFile(
      fixturePath("../../fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json"),
      "utf8"
    ));
    index.bundle_artifacts[0].sha256 = "0".repeat(64);
    await writeFile(tamperedPath, `${JSON.stringify(index, null, 2)}\n`, "utf8");

    const verification = await verifyAuditBundleIndex(tamperedPath, {
      workspaceRoot: fixturePath("../../"),
      generatedAt: "2026-07-07T00:00:00.000Z"
    });

    assert.equal(verification.status, "failed");
    assert.equal(verification.process_exit_code, 1);
    assert.equal(verification.root_hash.passed, false);
    assert.ok(verification.findings.some((finding) => finding.id === "bundle_root_hash_mismatch"));
    assert.ok(verification.findings.some((finding) => finding.id === "artifact_hash_mismatch"));
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test("A3 gate CLI verify-index writes machine and human verification reports", async () => {
  const tempDir = await mkdtemp(join(tmpdir(), "a3-gate-cli-verify-"));
  const paths = {
    json: join(tempDir, "bundle-verification.json"),
    markdown: join(tempDir, "bundle-verification.md")
  };
  try {
    const command = fixturePath("../../services/report/a3_gate_cli.mjs");
    const completed = await execFileAsync(process.execPath, [
      command,
      "--verify-index", "fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json",
      "--generated-at", "2026-07-07T00:00:00.000Z",
      "--output-json", paths.json,
      "--output-md", paths.markdown,
      "--strict-exit",
      "--json"
    ], {
      cwd: fixturePath("../../"),
      maxBuffer: 1024 * 1024
    });

    assert.equal(completed.stderr, "");
    const stdoutPayload = JSON.parse(completed.stdout);
    const jsonPayload = JSON.parse(await readFile(paths.json, "utf8"));
    const markdown = await readFile(paths.markdown, "utf8");

    assert.equal(stdoutPayload.status, "passed");
    assert.equal(jsonPayload.status, "passed");
    assert.equal(jsonPayload.process_exit_code, 0);
    assert.match(markdown, /Audit Bundle Verification/);
    assert.match(markdown, /Root hash: passed/);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test("A3 gate CLI redacts sensitive strings before output", async () => {
  const email = ["release.owner", "example.com"].join("@");
  const apiKeyAssignment = "RELEASEFOUNDRY_API_KEY" + "=secret-value";
  const bearerValue = ["Bearer", "abc.def"].join(" ");
  const signedUrl = ["https://media.example.invalid/file?", "Sign", "ature=secret"].join("");
  const payload = await buildGateCliPayload({
    runs: "fixtures/a3/mock_run_results.json",
    grades: "fixtures/a3/mock_grade_results.json",
    thresholds: "fixtures/a3/release_gate_thresholds.json",
    releaseVersion: "redaction-smoke",
    source: `${email} ${apiKeyAssignment} ${bearerValue} ${signedUrl}`,
    noFail: true
  });
  const text = JSON.stringify(payload);

  assert.equal(text.includes(email), false);
  assert.equal(text.includes("secret-value"), false);
  assert.equal(text.includes(bearerValue), false);
  assert.equal(text.includes(signedUrl), false);
  assert.ok(payload.redaction_log.replacement_count >= 4);
});

test("A3 gate CLI redacted evidence fixture preserves audit manifest shape", async () => {
  const payload = JSON.parse(await readFile(
    fixturePath("../../fixtures/a3/p3/a3_gate_cli_mock_blocked.redacted.json"),
    "utf8"
  ));

  assert.equal(payload.schema_version, "a3.gate_cli.v1");
  assert.equal(payload.release_gate.decision, "block_release");
  assert.equal(payload.release_workflow.github_check.conclusion, "failure");
  assert.equal(payload.audit_manifest.schema_version, "a3.gate_cli.audit_manifest.v1");
  const windowsDrivePrefix = ["C", ":"].join("") + "/";
  assert.ok(payload.audit_manifest.artifacts.every((artifact) => !artifact.path.includes(windowsDrivePrefix)));
  assert.ok(payload.audit_manifest.artifacts.every((artifact) => !artifact.path.includes("Users/")));
  assert.ok(payload.audit_manifest.artifacts.every((artifact) => /^[a-f0-9]{64}$/.test(artifact.sha256)));
});

test("A3 gate CLI committed PR artifacts preserve check and comment shapes", async () => {
  const check = JSON.parse(await readFile(
    fixturePath("../../fixtures/a3/p3/a3_gate_cli_github_check.redacted.json"),
    "utf8"
  ));
  const comment = await readFile(
    fixturePath("../../fixtures/a3/p3/a3_gate_cli_pr_comment.redacted.md"),
    "utf8"
  );
  const report = await readFile(
    fixturePath("../../fixtures/a3/p3/a3_gate_cli_report.redacted.md"),
    "utf8"
  );
  const manifest = JSON.parse(await readFile(
    fixturePath("../../fixtures/a3/p3/a3_gate_cli_generated_artifact_manifest.redacted.json"),
    "utf8"
  ));
  const bundle = JSON.parse(await readFile(
    fixturePath("../../fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json"),
    "utf8"
  ));
  const bundleVerification = JSON.parse(await readFile(
    fixturePath("../../fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json"),
    "utf8"
  ));

  assert.equal(check.name, "ReleaseFoundry Release Gate");
  assert.equal(check.conclusion, "failure");
  assert.equal(check.output.annotations.length, 5);
  assert.equal(check.output.annotations.every((item) => item.annotation_level === "failure"), true);
  assert.match(comment, /Decision: \*\*Block release\*\*/);
  assert.match(comment, /Required Reviewers/);
  assert.match(report, /# ReleaseFoundry Gate CLI Report/);
  assert.match(report, /## Audit Manifest/);
  assert.match(report, /## Waiver Review/);
  assert.match(report, /## Approval Review/);
  assert.equal(manifest.schema_version, "a3.generated_artifact_manifest.v1");
  assert.equal(manifest.generated_artifacts.length, 4);
  assert.ok(manifest.generated_artifacts.every((artifact) => /^[a-f0-9]{64}$/.test(artifact.sha256)));
  assert.ok(manifest.generated_artifacts.every((artifact) => !artifact.path.includes("Users/")));
  assert.equal(bundle.schema_version, "a3.audit_bundle_index.v1");
  assert.match(bundle.bundle_root_hash, /^[a-f0-9]{64}$/);
  assert.ok(bundle.bundle_artifacts.every((artifact) => !artifact.path.includes("Users/")));
  assert.ok(bundle.chain_of_custody.every((event) => /^[a-f0-9]{64}$/.test(event.event_hash)));
  assert.equal(bundleVerification.schema_version, "a3.audit_bundle_verification.v1");
  assert.equal(bundleVerification.status, "passed");
  assert.equal(bundleVerification.root_hash.passed, true);
  assert.ok(bundleVerification.artifacts.results.every((artifact) => !artifact.path.includes("Users/")));
});
