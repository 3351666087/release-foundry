#!/usr/bin/env node
import { execFile } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { promisify } from "node:util";

import {
  buildA3CandidateDeliveryBinding,
  buildA3SharedCandidateIdentity,
  verifyA3CandidateDeliveryArtifacts
} from "../services/report/a3_candidate_delivery_binding.mjs";
import {
  verifyAuditArchiveManifest,
  writeAuditArchiveManifest
} from "../services/report/a3_audit_archive.mjs";
import { verifyAuditBundleIndex } from "../services/report/a3_gate_cli.mjs";
import { verifyReleaseArtifactManifest } from "../services/report/a3_release_delivery.mjs";
import { buildReleaseDeliveryOutputs } from "../services/report/a3_release_delivery_cli.mjs";
import { evaluateA2TrustedReleaseAuthority } from "../services/report/a3_trusted_release_authority.mjs";

const execFileAsync = promisify(execFile);
const ROOT = resolve(import.meta.dirname, "..");
const RC3 = join(ROOT, "fixtures/a3/golden-path/rc3");
const EXPECTED = Object.freeze({
  candidateId: "a3-golden-agent@0.2.0-rc.3",
  runId: "a3-golden-20260720-003",
  releaseVersion: "0.2.0-rc.3",
  a1SourceCommit: "1d292047e991995fdf52f0545ffff410ee19a171",
  a1EvidenceBundleHash: "sha256:3240e097cc4e793520d9bbb0b2a600081a5440c751bf842cbe3b8cc9e495cd9f",
  a2AuthorityCommit: "d3529c356e49ce8502c050f0dad44020031ee0dd",
  a2DecisionHead: "sha256:bc608df9825ea316b374797ef76b4921bff4f6cee1943600d0297783e6be6303",
  a2GradesHash: "sha256:ffeba9ab8d7a2ccfb26ca8e135448cc9a2e6c8ead5b49837f77e5e73606a5304"
});
const FILES = Object.freeze({
  run: "a3_new_run_result.redacted.json",
  grades: "a2_grade_results.json",
  a2Identity: "a2_shared_candidate_identity.json",
  spine: "a2_trusted_spine_handoff.snapshot.json",
  a3Identity: "a3_shared_candidate_identity.json",
  deliveryBinding: "a3_candidate_delivery_binding.json",
  deploymentProbe: "deployment_probe.redacted.json",
  gateJson: "gate-report.json",
  gateMarkdown: "gate-report.md",
  githubCheck: "github-check.json",
  prComment: "pr-comment.md",
  generatedManifest: "generated-artifact-manifest.json",
  auditBundle: "audit-bundle-index.json",
  auditBundleVerification: "audit-bundle-verification.json",
  auditArchive: "audit-archive-manifest.json",
  auditArchiveVerification: "audit-archive-verification.json",
  releaseManifest: "release-artifact-manifest.json",
  releaseVerification: "release-artifact-verification.json",
  deliveryIndex: "release-delivery-index.json",
  deploymentAcceptance: "deployment-acceptance.json",
  goldenPath: "golden-path-status.json",
  goldenPathMarkdown: "golden-path-summary.md"
});

async function build(options = {}) {
  await mkdir(RC3, { recursive: true });
  const generatedAt = options.generatedAt || new Date().toISOString();
  const implementationCommit = options.implementationCommit || await currentGitCommit();
  assertGitSha(implementationCommit, "A3 implementation commit");
  const inputs = await sourceInputs();
  assertUpstream(inputs);

  const a3SharedIdentity = buildA3SharedCandidateIdentity(inputs, {
    a3GitSha: implementationCommit,
    releaseVersion: EXPECTED.releaseVersion
  });
  const candidateDeliveryBinding = buildA3CandidateDeliveryBinding({
    ...inputs,
    a3SharedIdentity
  }, {
    a3GitSha: implementationCommit,
    releaseVersion: EXPECTED.releaseVersion,
    generatedAt
  });
  await Promise.all([
    writeJson(pathFor(FILES.a3Identity), a3SharedIdentity),
    writeJson(pathFor(FILES.deliveryBinding), candidateDeliveryBinding),
    writeJson(pathFor(FILES.deploymentProbe), deploymentProbe(generatedAt, implementationCommit))
  ]);

  await runGateCli({ generatedAt, implementationCommit });
  const bundleVerification = await verifyAuditBundleIndex(pathFor(FILES.auditBundle), {
    workspaceRoot: ROOT,
    noFail: false
  });
  if (bundleVerification.status !== "passed") throw new Error("Generated Audit Bundle failed verification.");
  await writeJson(pathFor(FILES.auditBundleVerification), bundleVerification);

  await writeAuditArchiveManifest({
    index: pathFor(FILES.auditBundle),
    output: pathFor(FILES.auditArchive),
    workspaceRoot: ROOT,
    generatedAt,
    source: "m40-05-rc3-local-candidate-binding"
  });
  const archiveVerification = await verifyAuditArchiveManifest(pathFor(FILES.auditArchive), {
    workspaceRoot: ROOT,
    verifiedAt: generatedAt,
    noFail: false
  });
  if (archiveVerification.status !== "passed") throw new Error("Generated Audit Archive failed verification.");
  await writeJson(pathFor(FILES.auditArchiveVerification), archiveVerification);

  await buildReleaseDeliveryOutputs({
    runs: pathFor(FILES.run),
    grades: pathFor(FILES.grades),
    trustedSpine: pathFor(FILES.spine),
    a2SharedCandidateIdentity: pathFor(FILES.a2Identity),
    a3SharedCandidateIdentity: pathFor(FILES.a3Identity),
    candidateDeliveryBinding: pathFor(FILES.deliveryBinding),
    a3ImplementationCommit: implementationCommit,
    auditBundle: pathFor(FILES.auditBundle),
    auditBundleVerification: pathFor(FILES.auditBundleVerification),
    auditArchive: pathFor(FILES.auditArchive),
    auditArchiveVerification: pathFor(FILES.auditArchiveVerification),
    deploymentProbe: pathFor(FILES.deploymentProbe),
    releaseVersion: EXPECTED.releaseVersion,
    environment: "staging",
    channel: "release-candidate",
    gitSha: EXPECTED.a1SourceCommit,
    generatedAt,
    verifiedAt: generatedAt,
    outputDir: RC3,
    workspaceRoot: ROOT,
    documentation: [
      "docs/a2/m40_04_rc3_candidate_authority_handoff.md",
      "docs/a3/m40_05_rc3_candidate_delivery_handoff.md"
    ],
    noFail: true
  });

  return check({ expectedImplementationCommit: implementationCommit });
}

async function check(options = {}) {
  const requiredFiles = Object.values(FILES);
  const missing = [];
  for (const file of requiredFiles) {
    try {
      await readFile(pathFor(file));
    } catch {
      missing.push(file);
    }
  }
  if (missing.length) throw new Error(`Missing rc.3 delivery artifacts: ${missing.join(", ")}`);

  const inputs = await sourceInputs();
  assertUpstream(inputs);
  const a3SharedIdentity = await readJson(pathFor(FILES.a3Identity));
  const candidateDeliveryBinding = await readJson(pathFor(FILES.deliveryBinding));
  const implementationCommit = options.expectedImplementationCommit
    || candidateDeliveryBinding.a3?.implementation_commit;
  const candidateVerification = verifyA3CandidateDeliveryArtifacts({
    ...inputs,
    a3SharedIdentity,
    candidateDeliveryBinding
  }, {
    a3GitSha: implementationCommit,
    releaseVersion: EXPECTED.releaseVersion
  });
  if (!candidateVerification.verified) {
    throw new Error(`Candidate binding verification failed: ${candidateVerification.blockers.join(", ")}`);
  }

  const authority = evaluateA2TrustedReleaseAuthority(inputs.a2TrustedSpine);
  if (!authority.integrity_verified) throw new Error("A2 Trusted Spine integrity is invalid.");
  if (authority.upstream_decision !== "block" || authority.release_ready !== false || authority.allowed !== false) {
    throw new Error("A3 did not preserve the authoritative A2 block.");
  }
  const gate = await readJson(pathFor(FILES.gateJson));
  assertEqual(gate.candidate_binding_verification?.verified, true, "gate candidate binding");
  assertEqual(gate.trusted_release_authority?.upstream_decision, "block", "gate A2 decision");
  assertEqual(gate.release_gate?.decision, "block_release", "gate decision");
  assertEqual(gate.process_exit_code, 0, "gate evidence generation exit code");

  const bundleVerification = await verifyAuditBundleIndex(pathFor(FILES.auditBundle), {
    workspaceRoot: ROOT,
    noFail: false
  });
  if (bundleVerification.status !== "passed") throw new Error("Committed Audit Bundle failed verification.");
  const archiveVerification = await verifyAuditArchiveManifest(pathFor(FILES.auditArchive), {
    workspaceRoot: ROOT,
    noFail: false
  });
  if (archiveVerification.status !== "passed") throw new Error("Committed Audit Archive failed verification.");
  const releaseManifest = await readJson(pathFor(FILES.releaseManifest));
  const releaseVerification = await verifyReleaseArtifactManifest(releaseManifest, {
    workspaceRoot: ROOT,
    verifiedAt: "check"
  });
  if (releaseVerification.status !== "passed") throw new Error("Committed release artifact manifest failed verification.");

  const index = await readJson(pathFor(FILES.deliveryIndex));
  const acceptance = await readJson(pathFor(FILES.deploymentAcceptance));
  const goldenPath = await readJson(pathFor(FILES.goldenPath));
  assertEqual(index.candidate_id, EXPECTED.candidateId, "delivery candidate ID");
  assertEqual(index.run_id, EXPECTED.runId, "delivery run ID");
  assertEqual(index.release_version, EXPECTED.releaseVersion, "delivery release version");
  assertEqual(index.candidate_binding?.verified, true, "delivery binding verification");
  assertEqual(index.candidate_binding?.a2_decision_ledger_head_hash, EXPECTED.a2DecisionHead, "delivery Decision Ledger head");
  assertEqual(index.candidate_binding?.a2_grades_hash, EXPECTED.a2GradesHash, "delivery grades hash");
  assertEqual(index.candidate_binding?.a3_implementation_commit, implementationCommit, "delivery implementation commit");
  assertEqual(index.authority?.a2_upstream_decision, "block", "delivery A2 decision");
  assertEqual(index.production_ready, false, "delivery production readiness");
  assertEqual(acceptance.production_accepted, false, "deployment acceptance");
  assertEqual(goldenPath.production_ready, false, "Golden Path production readiness");

  return {
    schema_version: "a3.m40_05_rc3_delivery_verification.v1",
    status: "passed",
    candidate_id: EXPECTED.candidateId,
    run_id: EXPECTED.runId,
    release_version: EXPECTED.releaseVersion,
    a3_implementation_commit: implementationCommit,
    a2_decision: authority.upstream_decision,
    a2_decision_ledger_head_hash: EXPECTED.a2DecisionHead,
    a2_grades_hash: EXPECTED.a2GradesHash,
    candidate_binding_verified: true,
    audit_bundle_verified: true,
    audit_archive_verified: true,
    release_artifact_verified: true,
    production_ready: false,
    safety: {
      a2_decision_recomputed: false,
      human_approval_claimed: false,
      production_authority_claimed: false,
      live_github_readback_reused: false,
      secrets_included: false
    }
  };
}

async function runGateCli({ generatedAt, implementationCommit }) {
  const args = [
    join(ROOT, "services/report/a3_gate_cli.mjs"),
    "--runs", pathFor(FILES.run),
    "--grades", pathFor(FILES.grades),
    "--coverage", join(ROOT, "fixtures/a2/results/a2_g3_coverage_report.json"),
    "--thresholds", join(ROOT, "fixtures/a3/release_gate_thresholds.json"),
    "--a2-trusted-spine", pathFor(FILES.spine),
    "--a2-shared-candidate-identity", pathFor(FILES.a2Identity),
    "--a3-shared-candidate-identity", pathFor(FILES.a3Identity),
    "--candidate-delivery-binding", pathFor(FILES.deliveryBinding),
    "--a3-implementation-commit", implementationCommit,
    "--deployment-probe", pathFor(FILES.deploymentProbe),
    "--release-version", EXPECTED.releaseVersion,
    "--environment", "staging",
    "--owner", "A3 release owner",
    "--generated-at", generatedAt,
    "--source", "m40-05-rc3-local-candidate-binding",
    "--head-sha", EXPECTED.a1SourceCommit,
    "--output-json", pathFor(FILES.gateJson),
    "--output-md", pathFor(FILES.gateMarkdown),
    "--output-check", pathFor(FILES.githubCheck),
    "--output-pr-comment", pathFor(FILES.prComment),
    "--output-manifest", pathFor(FILES.generatedManifest),
    "--output-bundle", pathFor(FILES.auditBundle),
    "--no-fail",
    "--json"
  ];
  const completed = await execFileAsync(process.execPath, args, {
    cwd: ROOT,
    maxBuffer: 8 * 1024 * 1024
  });
  if (completed.stderr) throw new Error(`Gate CLI wrote to stderr: ${completed.stderr.slice(0, 500)}`);
}

async function sourceInputs() {
  return {
    runFixture: await readJson(pathFor(FILES.run)),
    gradeFixture: await readJson(pathFor(FILES.grades)),
    a2SharedIdentity: await readJson(pathFor(FILES.a2Identity)),
    a2TrustedSpine: await readJson(pathFor(FILES.spine))
  };
}

function assertUpstream(inputs) {
  const spine = inputs.a2TrustedSpine;
  const binding = spine.candidate_binding || {};
  assertEqual(binding.candidate_id, EXPECTED.candidateId, "candidate ID");
  assertEqual(binding.run_id, EXPECTED.runId, "run ID");
  assertEqual(binding.evidence_release_version, EXPECTED.releaseVersion, "release version");
  assertEqual(binding.a1_source_commit, EXPECTED.a1SourceCommit, "A1 source commit");
  assertEqual(binding.a1_evidence_bundle_hash, EXPECTED.a1EvidenceBundleHash, "A1 evidence bundle hash");
  assertEqual(binding.a2_authority_commit, EXPECTED.a2AuthorityCommit, "A2 authority commit");
  assertEqual(spine.decision_ledger?.head_hash, EXPECTED.a2DecisionHead, "A2 Decision Ledger head");
  assertEqual(spine.grade_results?.hash, EXPECTED.a2GradesHash, "A2 grades hash");
  assertEqual(inputs.runFixture.run_id, EXPECTED.runId, "A1 RunResult ID");
  assertEqual(inputs.a2SharedIdentity.a2?.decision_hash, EXPECTED.a2DecisionHead, "A2 identity decision hash");
  assertEqual(inputs.a2SharedIdentity.a2?.grades_hash, EXPECTED.a2GradesHash, "A2 identity grades hash");
}

function deploymentProbe(generatedAt, implementationCommit) {
  const notProven = (reason, evidenceClass = "not_proven") => ({
    status: "not_proven",
    verified: false,
    evidence_class: evidenceClass,
    reason
  });
  return {
    schema_version: "a3.deployment_probe.v1",
    generated_at: generatedAt,
    environment: "staging",
    release_version: EXPECTED.releaseVersion,
    git_sha_alias: EXPECTED.a1SourceCommit,
    ci_tested_sha_alias: null,
    a3_implementation_commit: implementationCommit,
    hosted_identity: notProven("No rc.3 hosted deployment identity receipt is attached.", "contract_only"),
    database: notProven("A2 PostgreSQL judge persistence is verified, but no rc.3 A3 hosted control-plane database receipt is attached.", "contract_only"),
    queue_worker: notProven("No deployed rc.3 queue, retry, dead-letter, and worker-health receipt is attached."),
    object_storage: notProven("The rc.3 Audit Bundle has not been written to and read back from immutable hosted object storage."),
    deployment_target: notProven("No staging or VPC deployment URL and versioned health receipt is configured."),
    upgrade_rollback: notProven("No authorized rc.3 production upgrade and rollback rehearsal receipt exists."),
    github_app: notProven("No tenant-bound GitHub App installation executed this rc.3 candidate delivery."),
    safety: {
      token_included: false,
      cookie_included: false,
      installation_token_included: false,
      fixture_claimed_as_production: false
    }
  };
}

async function currentGitCommit() {
  const result = await execFileAsync("git", ["rev-parse", "HEAD"], { cwd: ROOT });
  return result.stdout.trim();
}

function pathFor(file) {
  return join(RC3, file);
}

async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

async function writeJson(path, value) {
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function assertEqual(actual, expected, label) {
  if (actual !== expected) throw new Error(`${label} mismatch: expected ${expected}, received ${actual}`);
}

function assertGitSha(value, label) {
  if (!/^[0-9a-f]{40}$/.test(String(value || ""))) throw new Error(`${label} must be a full 40-character Git SHA.`);
}

function parseArgs(argv = []) {
  const options = { check: false, json: false };
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (item === "--check") options.check = true;
    else if (item === "--json") options.json = true;
    else if (item === "--implementation-commit") options.implementationCommit = argv[++index];
    else if (item === "--generated-at") options.generatedAt = argv[++index];
    else if (item === "--help" || item === "-h") options.help = true;
    else throw new Error(`Unknown argument: ${item}`);
  }
  return options;
}

async function main(argv = process.argv.slice(2)) {
  const options = parseArgs(argv);
  if (options.help) {
    process.stdout.write("Usage: node scripts/a3_build_m40_rc3_delivery.mjs [--implementation-commit <sha>] [--generated-at <ISO>] [--json]\n       node scripts/a3_build_m40_rc3_delivery.mjs --check [--json]\n");
    return 0;
  }
  const receipt = options.check ? await check() : await build(options);
  process.stdout.write(`${JSON.stringify(receipt, null, options.json ? 2 : 0)}\n`);
  return 0;
}

main().then((exitCode) => {
  process.exitCode = exitCode;
}).catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
});
