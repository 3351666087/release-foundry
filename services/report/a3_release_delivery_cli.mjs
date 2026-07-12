#!/usr/bin/env node
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  buildDeliveryGoldenPath,
  buildDeploymentAcceptance,
  buildReleaseArtifactManifest,
  describeArtifactFile,
  normalizeA2GradeReport,
  renderDeliveryGoldenPathMarkdown,
  summarizeA1RunEvidence,
  summarizeA2GradeEvidence,
  verifyReleaseArtifactManifest
} from "./a3_release_delivery.mjs";
import { evaluateA2TrustedReleaseAuthority } from "./a3_trusted_release_authority.mjs";

const DEFAULT_OUTPUT_NAMES = Object.freeze({
  manifest: "release-artifact-manifest.json",
  verification: "release-artifact-verification.json",
  acceptance: "deployment-acceptance.json",
  goldenPath: "golden-path-status.json",
  markdown: "golden-path-summary.md",
  index: "release-delivery-index.json"
});

export function parseReleaseDeliveryArgs(argv = []) {
  const options = {
    environment: "staging",
    channel: "release-candidate",
    outputDir: "artifacts/a3-release-delivery",
    noFail: false,
    documentation: []
  };
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    const next = () => argv[++index];
    if (item === "--runs") options.runs = next();
    else if (item === "--grades") options.grades = next();
    else if (item === "--trusted-spine") options.trustedSpine = next();
    else if (item === "--audit-bundle") options.auditBundle = next();
    else if (item === "--audit-bundle-verification") options.auditBundleVerification = next();
    else if (item === "--audit-archive") options.auditArchive = next();
    else if (item === "--audit-archive-verification") options.auditArchiveVerification = next();
    else if (item === "--github-check-readback") options.githubCheckReadback = next();
    else if (item === "--github-pr-comment-readback") options.githubPrCommentReadback = next();
    else if (item === "--github-required-check-proof") options.githubRequiredCheckProof = next();
    else if (item === "--github-actions-artifact-readback") options.githubActionsArtifactReadback = next();
    else if (item === "--deployment-probe") options.deploymentProbe = next();
    else if (item === "--release-version") options.releaseVersion = next();
    else if (item === "--environment") options.environment = next();
    else if (item === "--channel") options.channel = next();
    else if (item === "--git-sha") options.gitSha = next();
    else if (item === "--ci-tested-sha") options.ciTestedSha = next();
    else if (item === "--generated-at") options.generatedAt = next();
    else if (item === "--verified-at") options.verifiedAt = next();
    else if (item === "--output-dir") options.outputDir = next();
    else if (item === "--doc") options.documentation.push(next());
    else if (item === "--no-fail") options.noFail = true;
    else if (item === "--strict-exit") options.noFail = false;
    else if (item === "--json") options.json = true;
    else if (item === "--help" || item === "-h") options.help = true;
    else throw new Error(`Unknown argument: ${item}`);
  }
  return options;
}

export async function buildReleaseDeliveryOutputs(options = {}) {
  if (options.help) return usageReceipt();
  for (const field of ["runs", "grades", "trustedSpine", "auditBundle", "auditBundleVerification", "auditArchive", "auditArchiveVerification", "deploymentProbe", "releaseVersion"]) {
    if (!options[field]) throw new Error(`--${camelToKebab(field)} is required.`);
  }
  const workspaceRoot = resolve(options.workspaceRoot || process.cwd());
  const generatedAt = options.generatedAt || new Date().toISOString();
  const verifiedAt = options.verifiedAt || generatedAt;
  const runFixture = await readJson(options.runs);
  const gradeInput = await readJson(options.grades);
  const gradeFixture = normalizeA2GradeReport(gradeInput);
  const a2TrustedSpine = await readJson(options.trustedSpine);
  const auditBundle = await readJson(options.auditBundle);
  const auditBundleVerification = await readJson(options.auditBundleVerification);
  const auditArchive = await readJson(options.auditArchive);
  const auditArchiveVerification = await readJson(options.auditArchiveVerification);
  const githubCheckReadback = await readJsonOptional(options.githubCheckReadback);
  const githubPrCommentReadback = await readJsonOptional(options.githubPrCommentReadback);
  const githubRequiredCheckProof = await readJsonOptional(options.githubRequiredCheckProof);
  const githubActionsArtifactReadback = await readJsonOptional(options.githubActionsArtifactReadback);
  const deploymentProbe = await readJson(options.deploymentProbe);
  const trustedReleaseAuthority = evaluateA2TrustedReleaseAuthority(a2TrustedSpine);
  const a1RunSummary = summarizeA1RunEvidence(runFixture);
  const a2GradeSummary = summarizeA2GradeEvidence(gradeFixture);

  const artifactInputs = [
    ["a1_run_result", options.runs, "runtime_evidence", "A1"],
    ["a2_judge_service_response", options.grades, "judge_evidence", "A2"],
    ["a2_trusted_spine", options.trustedSpine, "release_authority", "A2"],
    ["audit_bundle_index", options.auditBundle, "audit_bundle", "A3"],
    ["audit_bundle_verification", options.auditBundleVerification, "verification_receipt", "A3"],
    ["audit_archive_manifest", options.auditArchive, "signed_archive", "A3"],
    ["audit_archive_verification", options.auditArchiveVerification, "verification_receipt", "A3"],
    ["deployment_probe", options.deploymentProbe, "deployment_evidence", "A1/A3"],
    ["github_check_readback", options.githubCheckReadback, "github_readback", "A3"],
    ["github_pr_comment_readback", options.githubPrCommentReadback, "github_readback", "A3"],
    ["github_required_check_proof", options.githubRequiredCheckProof, "repository_policy", "A3"],
    ["github_actions_artifact_readback", options.githubActionsArtifactReadback, "release_distribution_readback", "A3"]
  ].filter(([, path]) => Boolean(path));
  const artifacts = await Promise.all(artifactInputs.map(([id, path, role, sourceLane]) => describeArtifactFile(id, path, {
    workspaceRoot,
    role,
    sourceLane
  })));

  const releaseArtifactManifest = buildReleaseArtifactManifest({
    a1RunSummary,
    a2GradeSummary,
    trustedReleaseAuthority,
    artifacts,
    documentation: options.documentation,
    releaseVersion: options.releaseVersion,
    environment: options.environment,
    channel: options.channel,
    gitSha: options.gitSha,
    ciTestedSha: options.ciTestedSha,
    generatedAt
  });
  const outputDir = resolve(options.outputDir);
  await mkdir(outputDir, { recursive: true });
  const manifestPath = join(outputDir, DEFAULT_OUTPUT_NAMES.manifest);
  await writeJson(manifestPath, releaseArtifactManifest);
  const releaseArtifactVerification = await verifyReleaseArtifactManifest(releaseArtifactManifest, {
    workspaceRoot,
    verifiedAt
  });
  await writeJson(join(outputDir, DEFAULT_OUTPUT_NAMES.verification), releaseArtifactVerification);

  const common = {
    runFixture,
    gradeFixture,
    a1RunSummary,
    a2GradeSummary,
    a2TrustedSpine,
    trustedReleaseAuthority,
    auditBundle,
    auditBundleVerification,
    auditArchive,
    auditArchiveVerification,
    githubCheckReadback,
    githubPrCommentReadback,
    githubRequiredCheckProof,
    githubActionsArtifactReadback,
    deploymentProbe,
    releaseArtifactManifest,
    releaseArtifactVerification,
    releaseVersion: options.releaseVersion,
    environment: options.environment,
    gitSha: options.gitSha,
    ciTestedSha: options.ciTestedSha,
    generatedAt
  };
  const deploymentAcceptance = buildDeploymentAcceptance(common, common);
  const goldenPath = buildDeliveryGoldenPath({ ...common, deploymentAcceptance }, common);
  const markdown = renderDeliveryGoldenPathMarkdown(goldenPath, deploymentAcceptance, releaseArtifactManifest);
  await Promise.all([
    writeJson(join(outputDir, DEFAULT_OUTPUT_NAMES.acceptance), deploymentAcceptance),
    writeJson(join(outputDir, DEFAULT_OUTPUT_NAMES.goldenPath), goldenPath),
    writeFile(join(outputDir, DEFAULT_OUTPUT_NAMES.markdown), markdown, "utf8")
  ]);
  const index = {
    schema_version: "a3.release_delivery_index.v1",
    generated_at: generatedAt,
    release_version: options.releaseVersion,
    git_sha_alias: options.gitSha || null,
    ci_tested_sha_alias: options.ciTestedSha || options.gitSha || null,
    status: goldenPath.status,
    production_ready: goldenPath.production_ready,
    files: {
      release_artifact_manifest: DEFAULT_OUTPUT_NAMES.manifest,
      release_artifact_verification: DEFAULT_OUTPUT_NAMES.verification,
      deployment_acceptance: DEFAULT_OUTPUT_NAMES.acceptance,
      golden_path_status: DEFAULT_OUTPUT_NAMES.goldenPath,
      golden_path_summary: DEFAULT_OUTPUT_NAMES.markdown
    },
    authority: {
      a1_run_ids: a1RunSummary.run_ids,
      a2_upstream_decision: trustedReleaseAuthority.upstream_decision,
      a2_release_ready: trustedReleaseAuthority.release_ready,
      a3_recomputed_decision: false
    },
    safety: {
      token_included: false,
      raw_secret_values_allowed: false,
      production_claim_requires_acceptance: true
    }
  };
  await writeJson(join(outputDir, DEFAULT_OUTPUT_NAMES.index), index);
  return {
    index,
    releaseArtifactManifest,
    releaseArtifactVerification,
    deploymentAcceptance,
    goldenPath,
    outputDir
  };
}

export async function runReleaseDeliveryCli(argv = process.argv.slice(2), io = {}) {
  try {
    const options = parseReleaseDeliveryArgs(argv);
    const result = await buildReleaseDeliveryOutputs(options);
    if (options.help) {
      (io.stdout || process.stdout).write(`${JSON.stringify(result, null, 2)}\n`);
      return 0;
    }
    const summary = {
      schema_version: "a3.release_delivery_cli_receipt.v1",
      status: result.goldenPath.status,
      production_ready: result.goldenPath.production_ready,
      deployment_accepted: result.deploymentAcceptance.production_accepted,
      release_version: result.index.release_version,
      git_sha_alias: result.index.git_sha_alias,
      ci_tested_sha_alias: result.index.ci_tested_sha_alias,
      run_ids: result.index.authority.a1_run_ids,
      output_dir: portableOutputDir(result.outputDir),
      safety: {
        token_included: false,
        secret_values_allowed: false,
        a2_decision_recomputed: false
      }
    };
    if (options.json) (io.stdout || process.stdout).write(`${JSON.stringify(summary, null, 2)}\n`);
    return options.noFail || result.goldenPath.production_ready ? 0 : 1;
  } catch (error) {
    const payload = {
      schema_version: "a3.release_delivery_cli_error.v1",
      error: "release_delivery_cli_error",
      message: sanitizeError(error.message),
      safety: { token_included: false, secret_values_allowed: false }
    };
    (io.stderr || process.stderr).write(`${JSON.stringify(payload, null, 2)}\n`);
    return 1;
  }
}

function usageReceipt() {
  return {
    schema_version: "a3.release_delivery_cli_usage.v1",
    command: "node services/report/a3_release_delivery_cli.mjs --runs <a1-run.json> --grades <a2-service-response.json> --trusted-spine <a2-trusted-spine.json> --audit-bundle <bundle.json> --audit-bundle-verification <bundle-verification.json> --audit-archive <archive.json> --audit-archive-verification <archive-verification.json> --deployment-probe <probe.json> --github-actions-artifact-readback <artifact.json> --release-version 0.2.0-rc.1 --git-sha <candidate-sha> --ci-tested-sha <tested-sha> --output-dir artifacts/a3-release-delivery --no-fail --json",
    notes: [
      "The CLI consumes A1/A2 evidence and never recomputes A2 score, pass/fail, or release authority.",
      "Use --no-fail in evidence-producing CI when a blocked release must still upload its audit packet."
    ]
  };
}

async function readJson(path) {
  return JSON.parse(await readFile(resolve(path), "utf8"));
}

async function readJsonOptional(path) {
  return path ? readJson(path) : {};
}

async function writeJson(path, value) {
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function camelToKebab(value) {
  return String(value).replace(/[A-Z]/g, (char) => `-${char.toLowerCase()}`);
}

function portableOutputDir(path) {
  const relativePath = relative(process.cwd(), resolve(path));
  return relativePath.startsWith("..") || isAbsolute(relativePath)
    ? "[outside-workspace]"
    : relativePath.replaceAll("\\", "/");
}

function sanitizeError(value = "") {
  return String(value)
    .replace(/Bearer\s+[A-Za-z0-9._-]+/gi, "Bearer [REDACTED]")
    .replace(/gh[pousr]_[A-Za-z0-9_]+/gi, "[REDACTED_GITHUB_TOKEN]")
    .replace(/github_pat_[A-Za-z0-9_]+/gi, "[REDACTED_GITHUB_TOKEN]")
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[REDACTED_EMAIL]")
    .slice(0, 500);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  runReleaseDeliveryCli().then((exitCode) => {
    process.exitCode = exitCode;
  });
}
