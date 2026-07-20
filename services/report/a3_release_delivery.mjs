import { createHash } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
import { basename, isAbsolute, relative, resolve } from "node:path";

import { evaluateA2TrustedReleaseAuthority } from "./a3_trusted_release_authority.mjs";

export const A3_DEPLOYMENT_ACCEPTANCE_SCHEMA_VERSION = "a3.deployment_acceptance.v1";
export const A3_RELEASE_ARTIFACT_MANIFEST_SCHEMA_VERSION = "a3.release_artifact_manifest.v1";
export const A3_RELEASE_ARTIFACT_VERIFICATION_SCHEMA_VERSION = "a3.release_artifact_verification.v1";
export const A3_DELIVERY_GOLDEN_PATH_SCHEMA_VERSION = "a3.delivery_golden_path.v1";

const LIVE_EVIDENCE_CLASSES = new Set([
  "live_readback",
  "durable_runtime",
  "deployment_probe",
  "github_actions_app",
  "github_app_installation"
]);

export function normalizeA2GradeReport(value = {}) {
  if (isObject(value.result?.grade_report)) return value.result.grade_report;
  if (isObject(value.grade_report)) return value.grade_report;
  return isObject(value) ? value : {};
}

export function summarizeA1RunEvidence(runFixture = {}) {
  const roots = Array.isArray(runFixture.runs)
    ? runFixture.runs.filter(isObject)
    : isObject(runFixture.run_result)
      ? [runFixture.run_result]
      : Array.isArray(runFixture.cases)
        ? [runFixture]
        : [];
  const cases = roots.flatMap((run) => array(run.cases).filter(isObject));
  const runIds = roots.map((run) => text(run.run_id)).filter(Boolean);
  const traceEvents = cases.flatMap((item) => array(item.trace_events));
  const observations = cases.flatMap((item) => array(item.observations));
  const toolCalls = cases.flatMap((item) => {
    const actual = object(item.actual);
    const output = object(item.agent_output);
    return [
      ...array(actual.tool_calls),
      ...array(output.tool_calls),
      ...array(item.tool_calls),
      ...array(item.observations).flatMap((observation) => array(object(observation).tool_calls))
    ];
  });
  const completenessValues = roots
    .map((run) => normalizedRatio(run.trace_completeness))
    .filter((value) => value !== null);
  const traceCompleteness = completenessValues.length
    ? completenessValues.reduce((sum, value) => sum + value, 0) / completenessValues.length
    : cases.length
      ? cases.filter((item) => array(item.observations).length || array(item.trace_events).length).length / cases.length
      : 0;
  return {
    schema_version: "a3.a1_run_evidence_summary.v1",
    source_schema_version: text(runFixture.schema_version || roots[0]?.schema_version, "unknown"),
    run_ids: runIds,
    run_count: roots.length,
    case_count: cases.length,
    trace_event_count: traceEvents.length,
    observation_count: observations.length,
    tool_call_count: toolCalls.length,
    trace_completeness: round(traceCompleteness, 4),
    complete: roots.length > 0 && cases.length > 0 && traceCompleteness >= 1
  };
}

export function summarizeA2GradeEvidence(gradeInput = {}) {
  const report = normalizeA2GradeReport(gradeInput);
  const grades = array(report.grade_results).filter(isObject);
  return {
    schema_version: "a3.a2_grade_evidence_summary.v1",
    source_schema_version: text(report.schema_version, "unknown"),
    report_id: text(report.report_id, null),
    dataset_id: text(report.dataset_id, null),
    grade_count: grades.length,
    passed: grades.filter((item) => item.passed === true).length,
    failed: grades.filter((item) => item.passed === false).length,
    judge_result_count: grades.reduce((total, item) => total + array(item.judge_results).length, 0),
    case_ids: grades.map((item) => text(item.case_id)).filter(Boolean),
    authoritative_owner: "A2",
    a3_recomputed_score: false,
    a3_recomputed_decision: false
  };
}

export function buildDeploymentAcceptance(input = {}, options = {}) {
  const run = input.a1RunSummary || summarizeA1RunEvidence(input.runFixture || {});
  const grades = input.a2GradeSummary || summarizeA2GradeEvidence(input.gradeFixture || {});
  const authority = normalizeAuthority(input.trustedReleaseAuthority, input.a2TrustedSpine);
  const probe = object(input.deploymentProbe);
  const checkReadback = object(input.githubCheckReadback);
  const commentReadback = object(input.githubPrCommentReadback);
  const requiredCheck = object(input.githubRequiredCheckProof);
  const actionsArtifact = object(input.githubActionsArtifactReadback);
  const bundleVerification = object(input.auditBundleVerification);
  const archiveVerification = object(input.auditArchiveVerification);
  const artifactVerification = object(input.releaseArtifactVerification);
  const checks = [
    acceptanceCheck("a1_run_evidence", "A1 RunResult captured", run.complete, {
      owner: "A1",
      evidenceClass: "local_authoritative",
      evidenceRef: run.run_ids[0] || null,
      blockedReason: run.run_count ? "A1 trace evidence is incomplete." : "No A1 RunResult is attached."
    }),
    acceptanceCheck("a2_grade_join", "A2 GradeResult joined", grades.grade_count > 0 && grades.grade_count === run.case_count, {
      owner: "A2",
      evidenceClass: "local_authoritative",
      evidenceRef: grades.report_id,
      blockedReason: grades.grade_count
        ? "A1 case count and A2 GradeResult count do not match."
        : "No A2 GradeResult report is attached."
    }),
    acceptanceCheck("a2_release_authority", "A2 Decision Ledger allows release", authority.allowed === true, {
      owner: "A2",
      evidenceClass: authority.integrity_verified ? "local_authoritative" : "contract_only",
      evidenceRef: authority.decision_ledger?.head_hash || null,
      blockedReason: authority.reason_code || "A2 release authority is unavailable.",
      details: {
        integrity_verified: authority.integrity_verified === true,
        upstream_decision: authority.upstream_decision || "unknown",
        release_ready: authority.release_ready === true
      }
    }),
    probeCheck("hosted_identity", "A1 hosted identity verifier", probe.hosted_identity, "A1"),
    probeCheck("postgres_rls", "PostgreSQL migration and RLS", probe.database, "A1/A3"),
    probeCheck("queue_worker", "Durable queue worker", probe.queue_worker, "A1"),
    probeCheck("object_storage", "Immutable object storage", probe.object_storage, "A1/A3"),
    probeCheck("deployment_health", "Deployed health and version readback", probe.deployment_target, "A1/A3"),
    probeCheck("upgrade_rollback", "Upgrade and rollback rehearsal", probe.upgrade_rollback, "A1/A3"),
    probeCheck("github_app_installation", "Tenant-bound GitHub App installation", probe.github_app, "A1/A3"),
    acceptanceCheck("github_check_readback", "GitHub Check live readback", liveGitHubReadback(checkReadback, "check_run"), {
      owner: "A3",
      evidenceClass: liveGitHubReadback(checkReadback, "check_run") ? "live_readback" : readbackEvidenceClass(checkReadback),
      evidenceRef: checkReadback.readback_id || null,
      blockedReason: githubReadbackReason(checkReadback, "GitHub Check")
    }),
    acceptanceCheck("github_pr_comment_readback", "PR comment live readback", liveGitHubReadback(commentReadback, "pr_comment"), {
      owner: "A3",
      evidenceClass: liveGitHubReadback(commentReadback, "pr_comment") ? "live_readback" : readbackEvidenceClass(commentReadback),
      evidenceRef: commentReadback.readback_id || null,
      blockedReason: githubReadbackReason(commentReadback, "PR comment")
    }),
    acceptanceCheck("github_actions_artifact_readback", "GitHub Actions artifact live readback", liveGitHubActionsArtifactReadback(actionsArtifact, {
      candidateSha: options.gitSha || input.gitSha,
      ciTestedSha: options.ciTestedSha || input.ciTestedSha
    }), {
      owner: "A3",
      evidenceClass: liveGitHubActionsArtifactReadback(actionsArtifact, {
        candidateSha: options.gitSha || input.gitSha,
        ciTestedSha: options.ciTestedSha || input.ciTestedSha
      }) ? "live_readback" : readbackEvidenceClass(actionsArtifact),
      evidenceRef: actionsArtifact.artifact_id_alias || null,
      blockedReason: "A versioned GitHub Actions artifact has not been downloaded and read back for this candidate.",
      details: {
        artifact_name: actionsArtifact.artifact_name || null,
        digest: actionsArtifact.digest || null,
        expired: actionsArtifact.expired ?? null
      }
    }),
    acceptanceCheck("required_check_enforcement", "Required Check enforced on main", requiredCheck.enforced === true && requiredCheck.readback_status === "readback_confirmed", {
      owner: "Repository maintainer",
      evidenceClass: requiredCheck.enforced === true ? "live_readback" : readbackEvidenceClass(requiredCheck),
      evidenceRef: requiredCheck.proof_id || null,
      blockedReason: requiredCheck.readback_status === "missing"
        ? "main has no branch protection or the required check is absent."
        : "Required-check enforcement has not been read back from GitHub."
    }),
    acceptanceCheck("audit_bundle_verification", "Audit Bundle verified", bundleVerification.status === "passed" && bundleVerification.root_hash?.passed === true, {
      owner: "A3",
      evidenceClass: "local_verification",
      evidenceRef: bundleVerification.verification_id || bundleVerification.bundle_id || null,
      blockedReason: "Audit Bundle verification is missing or failed."
    }),
    acceptanceCheck("audit_archive_verification", "Signed audit archive verified", archiveVerification.status === "passed" && archiveVerification.root_hash?.passed === true && archiveVerification.signature?.passed === true, {
      owner: "A3",
      evidenceClass: "local_verification",
      evidenceRef: archiveVerification.verification_id || archiveVerification.archive_id || null,
      blockedReason: "Signed archive verification is missing or failed."
    }),
    acceptanceCheck("release_artifact_verification", "Versioned release artifact verified", artifactVerification.status === "passed", {
      owner: "A3",
      evidenceClass: "local_verification",
      evidenceRef: artifactVerification.manifest_hash || null,
      blockedReason: "Release artifact verification is missing or failed."
    })
  ];
  const blockingChecks = checks.filter((item) => item.required && item.status !== "passed");
  const generatedAt = options.generatedAt || input.generatedAt || "runtime";
  const identity = {
    release_version: options.releaseVersion || input.releaseVersion || "unknown-release",
    environment: options.environment || input.environment || text(probe.environment, "unknown"),
    git_sha_alias: options.gitSha || input.gitSha || text(probe.git_sha_alias, null),
    ci_tested_sha_alias: options.ciTestedSha || input.ciTestedSha || text(probe.ci_tested_sha_alias, null),
    run_ids: run.run_ids
  };
  const acceptanceId = `dpa_${sha256(stableJson({ identity, checks })).slice(0, 20)}`;
  return {
    schema_version: A3_DEPLOYMENT_ACCEPTANCE_SCHEMA_VERSION,
    acceptance_id: acceptanceId,
    generated_at: generatedAt,
    status: blockingChecks.length ? "blocked" : "accepted",
    production_accepted: blockingChecks.length === 0,
    release_identity: identity,
    summary: {
      total_checks: checks.length,
      passed: checks.filter((item) => item.status === "passed").length,
      blocked: checks.filter((item) => item.status === "blocked").length,
      not_proven: checks.filter((item) => item.status === "not_proven").length,
      failed: checks.filter((item) => item.status === "failed").length
    },
    checks,
    blocking_check_ids: blockingChecks.map((item) => item.id),
    next_actions: blockingChecks.slice(0, 5).map((item) => ({
      check_id: item.id,
      owner: item.owner,
      action: item.blocked_reason
    })),
    authority: {
      runtime_and_identity: "A1",
      judge_and_release_decision: "A2",
      product_workflow_and_packaging: "A3",
      repository_policy: "GitHub repository maintainer"
    },
    safety: {
      fixture_claimed_as_production: false,
      dry_run_claimed_as_live: false,
      a2_decision_recomputed: false,
      raw_secret_values_allowed: false,
      token_included: false
    }
  };
}

export function buildReleaseArtifactManifest(input = {}, options = {}) {
  const releaseVersion = options.releaseVersion || input.releaseVersion || "unknown-release";
  const run = input.a1RunSummary || summarizeA1RunEvidence(input.runFixture || {});
  const grades = input.a2GradeSummary || summarizeA2GradeEvidence(input.gradeFixture || {});
  const authority = normalizeAuthority(input.trustedReleaseAuthority, input.a2TrustedSpine);
  const artifacts = array(input.artifacts)
    .filter(isObject)
    .map(normalizeArtifactDescriptor)
    .sort((left, right) => `${left.role}:${left.id}:${left.path}`.localeCompare(`${right.role}:${right.id}:${right.path}`));
  const manifestCore = {
    schema_version: A3_RELEASE_ARTIFACT_MANIFEST_SCHEMA_VERSION,
    release: {
      version: releaseVersion,
      channel: options.channel || input.channel || "release-candidate",
      environment: options.environment || input.environment || "staging",
      git_sha_alias: options.gitSha || input.gitSha || null,
      ci_tested_sha_alias: options.ciTestedSha || input.ciTestedSha || null,
      run_ids: run.run_ids,
      candidate_only: authority.allowed !== true,
      production_release: false
    },
    authority: {
      a1_run_schema_version: run.source_schema_version,
      a2_grade_schema_version: grades.source_schema_version,
      a2_decision_ledger_head_hash: authority.decision_ledger?.head_hash || null,
      a2_decision_record_id: authority.decision_ledger?.record_id || null,
      a2_integrity_verified: authority.integrity_verified === true,
      a2_upstream_decision: authority.upstream_decision || "unknown",
      a2_release_ready: authority.release_ready === true,
      a3_recomputed_score: false,
      a3_recomputed_decision: false
    },
    compatibility: {
      a1: ["ashr.clone.run_result.v1", "a1.run_fixture.v1"],
      a2: ["a2.grade_results.v1", "a2.trusted_spine_handoff.v1", "a2.decision_ledger.v1"],
      a3: [A3_DEPLOYMENT_ACCEPTANCE_SCHEMA_VERSION, A3_DELIVERY_GOLDEN_PATH_SCHEMA_VERSION],
      required_scope: ["organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"]
    },
    artifact_set: {
      hash_algorithm: "sha256",
      artifact_count: artifacts.length,
      artifacts
    },
    documentation: array(input.documentation).map((item) => String(item).replaceAll("\\", "/")),
    distribution: {
      format: "portable-directory-uploaded-as-github-actions-artifact",
      github_release_created: false,
      deployment_created: false,
      install_upgrade_rollback_required_before_production: true
    },
    generated_at: options.generatedAt || input.generatedAt || "runtime",
    safety: {
      manifest_self_hash_excluded: true,
      local_absolute_paths_allowed: false,
      raw_secret_values_allowed: false,
      private_key_included: false,
      fixture_claimed_as_production: false
    }
  };
  return {
    ...manifestCore,
    artifact_set_hash: sha256(stableJson(artifacts)),
    manifest_hash: sha256(stableJson(manifestCore))
  };
}

export async function verifyReleaseArtifactManifest(manifestOrPath, options = {}) {
  const workspaceRoot = resolve(options.workspaceRoot || process.cwd());
  const manifest = typeof manifestOrPath === "string"
    ? JSON.parse(await readFile(resolve(manifestOrPath), "utf8"))
    : object(manifestOrPath);
  const findings = [];
  if (manifest.schema_version !== A3_RELEASE_ARTIFACT_MANIFEST_SCHEMA_VERSION) {
    findings.push(finding("schema_version", "blocking", "Release artifact manifest schema is invalid."));
  }
  const { manifest_hash: expectedManifestHash, artifact_set_hash: expectedArtifactSetHash, ...manifestCore } = manifest;
  const actualManifestHash = sha256(stableJson(manifestCore));
  if (expectedManifestHash !== actualManifestHash) {
    findings.push(finding("manifest_hash_mismatch", "blocking", "Release artifact manifest hash does not match canonical content."));
  }
  const artifacts = array(manifest.artifact_set?.artifacts).filter(isObject);
  const actualArtifactSetHash = sha256(stableJson(artifacts));
  if (expectedArtifactSetHash !== actualArtifactSetHash) {
    findings.push(finding("artifact_set_hash_mismatch", "blocking", "Artifact-set hash does not match the manifest list."));
  }
  const results = [];
  for (const artifact of artifacts) {
    results.push(await verifyArtifact(artifact, workspaceRoot));
  }
  for (const result of results) {
    if (result.status !== "passed" && result.required) {
      findings.push(finding(`artifact_${result.status}`, "blocking", `${result.id}: ${result.message}`));
    }
  }
  const passed = findings.every((item) => item.severity !== "blocking");
  return {
    schema_version: A3_RELEASE_ARTIFACT_VERIFICATION_SCHEMA_VERSION,
    status: passed ? "passed" : "failed",
    process_exit_code: passed ? 0 : 1,
    release_version: manifest.release?.version || "unknown-release",
    manifest_hash: expectedManifestHash || null,
    manifest_hash_passed: expectedManifestHash === actualManifestHash,
    artifact_set_hash_passed: expectedArtifactSetHash === actualArtifactSetHash,
    artifacts: {
      total: results.length,
      passed: results.filter((item) => item.status === "passed").length,
      failed: results.filter((item) => item.status !== "passed").length,
      results
    },
    findings,
    verified_at: options.verifiedAt || "runtime",
    safety: {
      raw_artifact_content_included: false,
      raw_secret_values_allowed: false,
      local_absolute_paths_exposed: false
    }
  };
}

export function buildDeliveryGoldenPath(input = {}, options = {}) {
  const run = input.a1RunSummary || summarizeA1RunEvidence(input.runFixture || {});
  const grades = input.a2GradeSummary || summarizeA2GradeEvidence(input.gradeFixture || {});
  const authority = normalizeAuthority(input.trustedReleaseAuthority, input.a2TrustedSpine);
  const acceptance = object(input.deploymentAcceptance);
  const artifact = object(input.releaseArtifactManifest);
  const artifactVerification = object(input.releaseArtifactVerification);
  const checkReadback = object(input.githubCheckReadback);
  const commentReadback = object(input.githubPrCommentReadback);
  const requiredCheck = object(input.githubRequiredCheckProof);
  const bundleVerification = object(input.auditBundleVerification);
  const archiveVerification = object(input.auditArchiveVerification);
  const stages = [
    stage("capture", "A1 captures a new run", "A1", run.complete, run.run_ids[0], "RunResult or complete trace evidence is missing."),
    stage("evaluate", "A2 grades every case", "A2", grades.grade_count > 0 && grades.grade_count === run.case_count, grades.report_id, "A2 grades do not cover every A1 case."),
    stage("decide", "A2 Decision Ledger authorizes release", "A2", authority.allowed === true, authority.decision_ledger?.head_hash, authority.reason_code || "A2 has not authorized release."),
    stage("bundle", "A3 seals and verifies the Audit Bundle", "A3", bundleVerification.status === "passed" && bundleVerification.root_hash?.passed === true, bundleVerification.bundle_id || bundleVerification.verification_id, "Audit Bundle verification is missing or failed."),
    stage("archive", "A3 verifies the signed archive", "A3", archiveVerification.status === "passed" && archiveVerification.signature?.passed === true, archiveVerification.archive_id || archiveVerification.verification_id, "Signed archive verification is missing or failed."),
    stage("package", "Versioned release artifact is verifiable", "A3", artifact.schema_version === A3_RELEASE_ARTIFACT_MANIFEST_SCHEMA_VERSION && artifactVerification.status === "passed", artifact.manifest_hash, "Release artifact manifest is missing or unverified."),
    stage("deploy", "Deployment acceptance passes", "A1/A3", acceptance.production_accepted === true, acceptance.acceptance_id, "Deployment acceptance is blocked."),
    stage("github_app", "Tenant GitHub App is trusted", "A1/A3", acceptanceCheckPassed(acceptance, "github_app_installation"), acceptance.acceptance_id, "A tenant-bound GitHub App installation is not proven."),
    stage("github_check", "GitHub Check is published and read back", "A3", liveGitHubReadback(checkReadback, "check_run"), checkReadback.readback_id, githubReadbackReason(checkReadback, "GitHub Check")),
    stage("pr_comment", "PR comment is published and read back", "A3", liveGitHubReadback(commentReadback, "pr_comment"), commentReadback.readback_id, githubReadbackReason(commentReadback, "PR comment")),
    stage("required_check", "main enforces the release check", "Repository maintainer", requiredCheck.enforced === true && requiredCheck.readback_status === "readback_confirmed", requiredCheck.proof_id, "Branch protection does not enforce the release check.")
  ];
  const blockers = stages.filter((item) => item.status !== "passed");
  const overallStatus = authority.integrity_verified !== true
    ? "integrity_invalid"
    : authority.allowed !== true
      ? "blocked_by_a2"
      : acceptance.production_accepted !== true
        ? "blocked_by_deployment"
        : blockers.length
          ? "blocked_by_delivery"
          : "ready";
  const generatedAt = options.generatedAt || input.generatedAt || "runtime";
  const pathId = `gpath_${sha256(stableJson({ stages, overallStatus, generatedAt })).slice(0, 20)}`;
  return {
    schema_version: A3_DELIVERY_GOLDEN_PATH_SCHEMA_VERSION,
    golden_path_id: pathId,
    generated_at: generatedAt,
    status: overallStatus,
    production_ready: overallStatus === "ready",
    release_version: options.releaseVersion || input.releaseVersion || artifact.release?.version || "unknown-release",
    run_ids: run.run_ids,
    stages,
    progress: {
      total: stages.length,
      passed: stages.filter((item) => item.status === "passed").length,
      blocked: blockers.length,
      percent: round((stages.filter((item) => item.status === "passed").length / stages.length) * 100, 1)
    },
    authoritative_release: {
      owner: "A2",
      integrity_verified: authority.integrity_verified === true,
      upstream_decision: authority.upstream_decision || "unknown",
      release_ready: authority.release_ready === true,
      blockers: array(authority.blockers)
    },
    next_actions: blockers.slice(0, 3).map((item) => ({
      stage_id: item.id,
      owner: item.owner,
      action: item.blocked_reason
    })),
    evidence_links: {
      deployment_acceptance_id: acceptance.acceptance_id || null,
      release_artifact_manifest_hash: artifact.manifest_hash || null,
      audit_bundle_verification_id: bundleVerification.verification_id || null,
      audit_archive_verification_id: archiveVerification.verification_id || null,
      github_check_readback_id: checkReadback.readback_id || null,
      github_pr_comment_readback_id: commentReadback.readback_id || null,
      required_check_proof_id: requiredCheck.proof_id || null
    },
    safety: {
      a1_runtime_recomputed: false,
      a2_score_recomputed: false,
      a2_decision_recomputed: false,
      dry_run_claimed_as_live: false,
      fixture_claimed_as_production: false,
      secret_values_allowed: false
    }
  };
}

export function renderDeliveryGoldenPathMarkdown(goldenPath = {}, acceptance = {}, artifact = {}) {
  const lines = [
    "# Ashr++ Release Delivery Golden Path",
    "",
    `- Status: ${goldenPath.status || "unknown"}`,
    `- Production ready: ${goldenPath.production_ready ? "yes" : "no"}`,
    `- Release version: ${goldenPath.release_version || artifact.release?.version || "unknown"}`,
    `- Progress: ${goldenPath.progress?.passed || 0}/${goldenPath.progress?.total || 0} (${goldenPath.progress?.percent || 0}%)`,
    `- Deployment acceptance: ${acceptance.status || "missing"}`,
    `- A2 decision: ${goldenPath.authoritative_release?.upstream_decision || "unknown"}`,
    "",
    "## Stages",
    ""
  ];
  for (const item of array(goldenPath.stages)) {
    lines.push(`- [${item.status === "passed" ? "x" : " "}] ${item.label} - ${item.status} (${item.owner})`);
    if (item.status !== "passed") lines.push(`  Reason: ${item.blocked_reason}`);
  }
  lines.push("", "## Safety", "", "A3 consumes A1 runtime evidence and A2 decisions. It does not recompute A2 score, pass/fail, or release authority.");
  return `${lines.join("\n")}\n`;
}

export async function describeArtifactFile(id, path, options = {}) {
  const workspaceRoot = resolve(options.workspaceRoot || process.cwd());
  const resolvedPath = resolve(path);
  const bytes = await readFile(resolvedPath);
  let schemaVersion = null;
  if (String(path).toLowerCase().endsWith(".json")) {
    try {
      schemaVersion = JSON.parse(bytes.toString("utf8")).schema_version || null;
    } catch {
      schemaVersion = null;
    }
  }
  return normalizeArtifactDescriptor({
    id,
    path: portablePath(resolvedPath, workspaceRoot),
    role: options.role || "release_evidence",
    required: options.required !== false,
    content_type: options.contentType || contentType(path),
    schema_version: schemaVersion,
    sha256: sha256(bytes),
    byte_size: bytes.length,
    source_lane: options.sourceLane || "A3"
  });
}

function normalizeAuthority(authority, spine) {
  if (isObject(authority) && authority.schema_version === "a3.trusted_release_authority.v1") return authority;
  return evaluateA2TrustedReleaseAuthority(isObject(spine) ? spine : {});
}

function acceptanceCheck(id, label, passed, options = {}) {
  const explicitFailure = options.failed === true;
  const evidenceClass = options.evidenceClass || "not_proven";
  const status = passed
    ? "passed"
    : explicitFailure
      ? "failed"
      : evidenceClass === "not_proven" || evidenceClass === "contract_only"
        ? "not_proven"
        : "blocked";
  return {
    id,
    label,
    owner: options.owner || "A3",
    required: options.required !== false,
    status,
    evidence_class: evidenceClass,
    evidence_ref: options.evidenceRef || null,
    blocked_reason: passed ? null : options.blockedReason || "Required evidence is not proven.",
    details: options.details || {},
    production_proof: passed && LIVE_EVIDENCE_CLASSES.has(evidenceClass)
  };
}

function probeCheck(id, label, value, owner) {
  const probe = object(value);
  const evidenceClass = text(probe.evidence_class, "not_proven");
  return acceptanceCheck(id, label, probe.verified === true && LIVE_EVIDENCE_CLASSES.has(evidenceClass), {
    owner,
    evidenceClass,
    evidenceRef: probe.evidence_ref || probe.receipt_id || null,
    failed: probe.status === "failed",
    blockedReason: text(probe.reason, `${label} has no live deployment proof.`),
    details: {
      status: text(probe.status, "unknown"),
      verified: probe.verified === true,
      observed_at: probe.observed_at || null
    }
  });
}

function stage(id, label, owner, passed, evidenceRef, blockedReason) {
  return {
    id,
    label,
    owner,
    status: passed ? "passed" : "blocked",
    evidence_ref: evidenceRef || null,
    blocked_reason: passed ? null : blockedReason
  };
}

function acceptanceCheckPassed(acceptance, id) {
  return array(acceptance.checks).some((item) => object(item).id === id && object(item).status === "passed");
}

function liveGitHubReadback(receipt, kind) {
  const value = object(receipt);
  const observed = object(value.observed);
  const expectedKind = kind === "check_run" ? "check_run" : "pr_comment";
  const url = text(observed.html_url, "");
  return value.provider === "github"
    && value.resource_kind === expectedKind
    && value.readback_status === "readback_confirmed"
    && value.readback_confirmed === true
    && value.calibration?.live_readback === true
    && /^https:\/\/github\.com\//i.test(url);
}

function readbackEvidenceClass(receipt) {
  if (receipt?.readback_status === "readback_confirmed") return "contract_only";
  return "not_proven";
}

function githubReadbackReason(receipt, label) {
  const status = text(receipt?.readback_status, "missing");
  if (status === "readback_confirmed" && receipt?.calibration?.live_readback !== true) {
    return `${label} is only a fixture/contract receipt, not a live github.com readback.`;
  }
  return `${label} live readback status is ${status}.`;
}

function liveGitHubActionsArtifactReadback(receipt = {}, expected = {}) {
  const value = object(receipt);
  return value.provider === "github"
    && value.resource_kind === "actions_artifact"
    && value.readback_status === "readback_confirmed"
    && value.readback_confirmed === true
    && value.expired === false
    && value.download_observed === true
    && /^sha256:[0-9a-f]{64}$/i.test(text(value.digest))
    && (!expected.candidateSha || value.candidate_head_sha_alias === expected.candidateSha)
    && (!expected.ciTestedSha || value.ci_tested_sha_alias === expected.ciTestedSha)
    && value.embedded_verification?.release_artifact_manifest === "passed"
    && value.embedded_verification?.production_release === false;
}

function normalizeArtifactDescriptor(value = {}) {
  return {
    id: text(value.id, "unknown-artifact"),
    path: safePortablePath(value.path),
    role: text(value.role || value.bundle_role, "release_evidence"),
    source_lane: text(value.source_lane, "A3"),
    required: value.required !== false,
    content_type: text(value.content_type, contentType(value.path)),
    schema_version: value.schema_version || null,
    sha256: text(value.sha256, null),
    byte_size: Number.isFinite(Number(value.byte_size)) ? Number(value.byte_size) : null
  };
}

async function verifyArtifact(artifact, workspaceRoot) {
  const normalized = normalizeArtifactDescriptor(artifact);
  if (!normalized.path || normalized.path.startsWith("[outside-workspace]")) {
    return { ...normalized, status: "outside_workspace", message: "Artifact path is outside the workspace." };
  }
  const resolvedPath = resolve(workspaceRoot, normalized.path);
  const relativePath = relative(workspaceRoot, resolvedPath);
  if (relativePath.startsWith("..") || isAbsolute(relativePath)) {
    return { ...normalized, status: "outside_workspace", message: "Artifact path escapes the workspace." };
  }
  try {
    const bytes = await readFile(resolvedPath);
    const fileStat = await stat(resolvedPath);
    if (sha256(bytes) !== normalized.sha256) {
      return { ...normalized, status: "hash_mismatch", message: "Artifact SHA-256 does not match." };
    }
    if (fileStat.size !== normalized.byte_size) {
      return { ...normalized, status: "size_mismatch", message: "Artifact byte size does not match." };
    }
    return { ...normalized, status: "passed", message: "Artifact hash and byte size match." };
  } catch (error) {
    return { ...normalized, status: "missing", message: `Artifact cannot be read: ${sanitizeError(error.message)}` };
  }
}

function finding(id, severity, message) {
  return { id, severity, message };
}

function portablePath(path, workspaceRoot) {
  const relativePath = relative(workspaceRoot, path);
  if (relativePath.startsWith("..") || isAbsolute(relativePath)) return `[outside-workspace]/${basename(path)}`;
  return relativePath.replaceAll("\\", "/");
}

function safePortablePath(path) {
  const normalized = text(path, "").replaceAll("\\", "/");
  if (/^[A-Za-z]:\//.test(normalized) || normalized.startsWith("/") || normalized.includes("../")) {
    return normalized ? `[outside-workspace]/${basename(normalized)}` : "";
  }
  return normalized;
}

function contentType(path = "") {
  const value = String(path).toLowerCase();
  if (value.endsWith(".json")) return "application/json";
  if (value.endsWith(".md")) return "text/markdown";
  if (value.endsWith(".html")) return "text/html";
  if (value.endsWith(".csv")) return "text/csv";
  return "application/octet-stream";
}

function normalizedRatio(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  return number > 1 ? number / 100 : number;
}

function round(value, digits) {
  const scale = 10 ** digits;
  return Math.round((Number(value) + Number.EPSILON) * scale) / scale;
}

function sanitizeError(value = "") {
  return String(value)
    .replace(/Bearer\s+[A-Za-z0-9._-]+/gi, "Bearer [REDACTED]")
    .replace(/gh[pousr]_[A-Za-z0-9_]+/gi, "[REDACTED_GITHUB_TOKEN]")
    .slice(0, 240);
}

function text(value, fallback = "") {
  if (value === undefined || value === null || value === "") return fallback;
  return String(value);
}

function object(value) {
  return isObject(value) ? value : {};
}

function array(value) {
  return Array.isArray(value) ? value : [];
}

function isObject(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function stableJson(value) {
  return JSON.stringify(sortValue(value));
}

function sortValue(value) {
  if (Array.isArray(value)) return value.map(sortValue);
  if (isObject(value)) {
    return Object.fromEntries(Object.entries(value)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => [key, sortValue(item)]));
  }
  return value;
}
