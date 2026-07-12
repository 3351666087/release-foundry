#!/usr/bin/env node
import { createHash } from "node:crypto";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import { basename, dirname, isAbsolute, relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import {
  buildDashboardSummary,
  summarizeReleaseGate,
  summarizeReleaseWorkflow
} from "./report_builder.mjs";
import { redactExport } from "./export_redaction_firewall.mjs";
import { normalizeA2GradeReport } from "./a3_release_delivery.mjs";
import { evaluateA2TrustedReleaseAuthority } from "./a3_trusted_release_authority.mjs";

export async function buildGateCliPayload(options = {}) {
  const workspaceRoot = resolve(options.workspaceRoot || process.cwd());
  const runs = await loadJsonRequired(options.runs, "runs");
  const gradesInput = await loadJsonRequired(options.grades, "grades");
  const grades = normalizeA2GradeReport(gradesInput);
  const coverage = await loadJsonOptional(options.coverage);
  const mediaSignedUrlCoverage = await loadJsonOptional(options.mediaSignedUrlCoverage);
  const thresholds = await loadJsonOptional(options.thresholds);
  const waiver = await loadJsonOptional(options.waiver);
  const approval = await loadJsonOptional(options.approval);
  const a2TrustedSpine = await loadJsonOptional(options.a2TrustedSpine);
  const trustedReleaseAuthority = a2TrustedSpine.schema_version === "a2.trusted_spine_handoff.v1"
    ? evaluateA2TrustedReleaseAuthority(a2TrustedSpine)
    : null;
  const summary = buildDashboardSummary(runs, grades);
  const localQualityGate = summarizeReleaseGate(runs, grades, coverage, mediaSignedUrlCoverage, { thresholds });
  const localWorkflow = summarizeReleaseWorkflow(runs, grades, coverage, mediaSignedUrlCoverage, {
    thresholds,
    release_version: options.releaseVersion,
    environment: options.environment,
    owner: options.owner
  });
  const authoritativeBlock = trustedReleaseAuthority && trustedReleaseAuthority.allowed !== true;
  const gate = authoritativeBlock
    ? projectTrustedAuthorityBlock(localQualityGate, trustedReleaseAuthority)
    : localQualityGate;
  const workflow = authoritativeBlock
    ? projectTrustedAuthorityWorkflow(localWorkflow, localQualityGate, trustedReleaseAuthority, summary, {
      headSha: options.headSha
    })
    : localWorkflow;
  const inputFiles = [
    inputArtifact("runs", options.runs, true, workspaceRoot),
    inputArtifact("grades", options.grades, true, workspaceRoot),
    inputArtifact("coverage", options.coverage, Boolean(options.coverage), workspaceRoot),
    inputArtifact("media_signed_url_coverage", options.mediaSignedUrlCoverage, Boolean(options.mediaSignedUrlCoverage), workspaceRoot),
    inputArtifact("thresholds", options.thresholds, Boolean(options.thresholds), workspaceRoot),
    inputArtifact("waiver", options.waiver, Boolean(options.waiver), workspaceRoot),
    inputArtifact("approval", options.approval, Boolean(options.approval), workspaceRoot)
  ].filter(Boolean);
  const artifacts = await Promise.all(inputFiles.map(async (artifact) => ({
    id: artifact.id,
    path: artifact.path,
    required: artifact.required,
    content_type: contentTypeForPath(artifact.path),
    sha256: await sha256File(artifact.resolved_path),
    byte_size: await byteSizeFile(artifact.resolved_path)
  })));

  const githubCheckRun = buildGithubCheckRunPayload(workflow, gate, summary, options);
  if (authoritativeBlock) {
    githubCheckRun.conclusion = "failure";
    githubCheckRun.output.title = `A2 blocked: ${summary.lastRunId || "unknown-run"}`;
    githubCheckRun.output.summary = `${githubCheckRun.output.summary}\n\nAuthoritative A2 status: ${trustedReleaseAuthority.status}; reason: ${trustedReleaseAuthority.reason_code}.`;
  }
  const blocksMerge = Boolean(gate.pr_gate.blocks_merge || authoritativeBlock);
  const rawPayload = {
    schema_version: "a3.gate_cli.v1",
    generated_at: options.generatedAt || "runtime",
    source: options.source || "local-fixtures",
    command_shape: "ashr gate --json",
    summary,
    local_quality_gate: localQualityGate,
    release_gate: gate,
    release_workflow: workflow,
    waiver_review: validateWaiverRequest(waiver, gate, workflow, summary, {
      generatedAt: options.generatedAt,
      releaseVersion: options.releaseVersion,
      environment: options.environment,
      headSha: options.headSha
    }),
    approval_review: validateApprovalRecord(approval, gate, workflow, summary, {
      waiver,
      generatedAt: options.generatedAt,
      releaseVersion: options.releaseVersion,
      environment: options.environment,
      headSha: options.headSha
    }),
    trusted_release_authority: trustedReleaseAuthority,
    github_check_run: githubCheckRun,
    pr_comment_markdown: workflow.pr_comment_markdown,
    audit_manifest: {
      schema_version: "a3.gate_cli.audit_manifest.v1",
      redaction_policy: "No API keys, cookies, tokens, emails, or live signed media URLs are allowed in CLI output.",
      artifacts
    },
    exit_mode: options.noFail ? "no-fail" : "strict-exit",
    exit_code_hint: blocksMerge ? 1 : 0,
    process_exit_code: options.noFail ? 0 : blocksMerge ? 1 : 0
  };
  const { value, replacement_count: replacementCount, findings, status } = redactExport(rawPayload, { surface: "gate_cli_payload" });
  return {
    ...value,
    redaction_log: {
      applied: true,
      status,
      replacement_count: replacementCount,
      finding_count: findings.length,
      rules_triggered: [...new Set(findings.map((finding) => finding.pattern_id))],
      policy: "Scrub emails, bearer tokens, API key assignments, generic secret tokens, cookies, and signed media URLs from CLI output."
    }
  };
}

function projectTrustedAuthorityBlock(localGate = {}, authority = {}) {
  const authorityCheck = {
    id: "a2_release_authority",
    passed: false,
    observed: `${authority.upstream_decision || "unknown"}; release_ready=${authority.release_ready === true}`,
    detail: `A2 Decision Ledger blocks release (${authority.reason_code || "authority_not_ready"}).`
  };
  const checks = [...arrayOf(localGate.checks).filter((item) => item?.id !== authorityCheck.id), authorityCheck];
  const failedChecks = [...new Set([...arrayOf(localGate.failed_checks), authorityCheck.id])];
  return {
    ...localGate,
    decision: "block_release",
    decision_label: "Block release",
    summary: `Local case-quality checks passed, but A2 Decision Ledger blocks release: ${authority.reason_code || "authority_not_ready"}.`,
    local_quality_decision: localGate.decision || "unknown",
    local_quality_decision_label: localGate.decision_label || "unknown",
    decision_authority: "A2 Decision Ledger",
    a2_upstream_decision: authority.upstream_decision || "unknown",
    a2_release_ready: authority.release_ready === true,
    checks,
    failed_check_count: failedChecks.length,
    failed_checks: failedChecks,
    required_approvers: [...new Set([...arrayOf(localGate.required_approvers), "A2 release authority owner"])],
    pr_gate: {
      ...localGate.pr_gate,
      status: "block_release",
      blocks_merge: true,
      warning_only: false
    }
  };
}

function projectTrustedAuthorityWorkflow(localWorkflow = {}, localGate = {}, authority = {}, summary = {}, options = {}) {
  const nextAction = `Do not merge or publish until A2 issues an allow Decision Ledger record for ${summary.lastRunId || "this run"}.`;
  const localCheck = localWorkflow.github_check || {};
  const localOutput = localCheck.output || {};
  const blockedRisk = {
    ...(localWorkflow.reviewer_workflow?.sign_off_risk || {}),
    level: "blocked",
    can_sign_off: false,
    risk_acceptance_required: false,
    executive_exception_required: false,
    reasons: [...new Set([
      ...arrayOf(localWorkflow.reviewer_workflow?.sign_off_risk?.reasons),
      authority.reason_code || "a2_release_authority_not_ready"
    ])],
    required_before_sign_off: [nextAction]
  };
  const prComment = renderTrustedAuthorityPrComment(localWorkflow, localGate, authority, summary, nextAction, options);
  return {
    ...localWorkflow,
    github_check: {
      ...localCheck,
      conclusion: "failure",
      blocks_merge: true,
      output: {
        ...localOutput,
        title: `A2 blocked: ${summary.lastRunId || "unknown-run"}`,
        summary: `Local case-quality gate: ${localGate.decision_label || localGate.decision || "unknown"}. Authoritative A2 decision: ${authority.upstream_decision || "unknown"}; release_ready=${authority.release_ready === true}.`,
        text: `${localOutput.text || ""}\n\nA2 Decision Ledger: ${authority.upstream_decision || "unknown"}\nA2 release_ready: ${authority.release_ready === true}\nNext action: ${nextAction}`.trim()
      }
    },
    pr_comment_markdown: prComment,
    waiver_policy: {
      ...(localWorkflow.waiver_policy || {}),
      required: false,
      allowed: false,
      exceptional_only: false,
      guidance: "A3 waiver and approval records cannot override an A2 Decision Ledger block."
    },
    reviewer_workflow: {
      ...(localWorkflow.reviewer_workflow || {}),
      state: "blocked_by_a2",
      next_actions: [nextAction],
      pr_gate_next_action: nextAction,
      sign_off_risk: blockedRisk,
      a2_release_gate: {
        schema_version: authority.schema_version || "a3.trusted_release_authority.v1",
        available: true,
        decision: authority.upstream_decision || "unknown",
        blocks_release: true,
        release_ready: authority.release_ready === true,
        blocker_types: arrayOf(authority.blockers),
        evidence_refs: [authority.decision_ledger?.head_hash, authority.decision_ledger?.record_id].filter(Boolean)
      }
    },
    reviewer_gate: {
      ...(localWorkflow.reviewer_gate || {}),
      pr_gate_next_action: nextAction,
      sign_off_risk: blockedRisk,
      a2_release_gate: {
        schema_version: authority.schema_version || "a3.trusted_release_authority.v1",
        available: true,
        decision: authority.upstream_decision || "unknown",
        blocks_release: true,
        release_ready: authority.release_ready === true,
        blocker_types: arrayOf(authority.blockers),
        evidence_refs: [authority.decision_ledger?.head_hash, authority.decision_ledger?.record_id].filter(Boolean)
      }
    }
  };
}

function renderTrustedAuthorityPrComment(localWorkflow = {}, localGate = {}, authority = {}, summary = {}, nextAction = "", options = {}) {
  const workflow = localWorkflow || {};
  return [
    `<!-- ashr-plus-plus:release-gate:${summary.lastRunId || "unknown-run"} -->`,
    "## Ashr++ Release Gate",
    "",
    "Decision: **Block release**",
    "Authority: **A2 Decision Ledger**",
    `Release: \`${workflow.release_version || "unknown-release"}\``,
    `Environment: \`${workflow.environment || "unknown"}\``,
    `Candidate SHA: \`${options.headSha || "not-bound"}\``,
    "",
    "| Signal | Value |",
    "|---|---|",
    `| Run | \`${summary.lastRunId || "unknown-run"}\` |`,
    `| A1/A2 case pass rate | ${summary.passRate ?? 0}% |`,
    `| Local quality gate | ${localGate.decision_label || localGate.decision || "unknown"} |`,
    `| Local quality risk score | ${localGate.risk_score ?? "unknown"} |`,
    `| Authoritative A2 decision | ${authority.upstream_decision || "unknown"} |`,
    `| A2 release ready | ${authority.release_ready === true ? "yes" : "no"} |`,
    `| Merge blocked | yes |`,
    "",
    "### Why blocked",
    "",
    ...arrayOf(authority.blockers).map((item) => `- \`${item}\``),
    "",
    "### Required action",
    "",
    `- ${nextAction}`,
    "- A3 did not recompute A2 scores, pass/fail, failure classes, or release authority.",
    "- An A3 waiver cannot convert this A2 block into approval.",
    ""
  ].join("\n");
}

export function renderGateCliMarkdown(payload = {}) {
  const gate = payload.release_gate || {};
  const workflow = payload.release_workflow || {};
  const summary = payload.summary || {};
  const artifacts = payload.audit_manifest?.artifacts || [];
  const waiverReview = payload.waiver_review || {};
  const approvalReview = payload.approval_review || {};
  const trustedAuthority = payload.trusted_release_authority || {};
  const lines = [
    "# Ashr++ Gate CLI Report",
    "",
    `- Command shape: ${payload.command_shape || "ashr gate --json"}`,
    `- Source: ${payload.source || "local-fixtures"}`,
    `- Run: ${summary.lastRunId || "unknown"}`,
    `- Decision: ${gate.decision_label || "unknown"}`,
    `- Risk score: ${gate.risk_score ?? "unknown"}`,
    `- Check conclusion: ${workflow.github_check?.conclusion || "unknown"}`,
    `- Blocks merge: ${gate.pr_gate?.blocks_merge || (trustedAuthority.schema_version && trustedAuthority.allowed !== true) ? "yes" : "no"}`,
    `- A2 authority: ${trustedAuthority.status || "not-attached"}`,
    `- A2 upstream decision: ${trustedAuthority.upstream_decision || "unknown"}`,
    `- A2 release ready: ${trustedAuthority.release_ready === true ? "yes" : "no"}`,
    `- Waiver: ${workflow.waiver_policy?.guidance || "unknown"}`,
    "",
    "## Audit Manifest",
    "",
    ...artifacts.map((artifact) => `- ${artifact.id}: ${artifact.sha256} (${artifact.path})`),
    "",
    "## Waiver Review",
    "",
    `- Status: ${waiverReview.status || "unknown"}`,
    `- Accepted: ${waiverReview.accepted ? "yes" : "no"}`,
    `- Automatic unblock: ${waiverReview.automatic_unblock ? "yes" : "no"}`,
    `- Reason: ${waiverReview.reason || "No waiver review available."}`,
    "",
    "## Approval Review",
    "",
    `- Status: ${approvalReview.status || "unknown"}`,
    `- Accepted: ${approvalReview.accepted ? "yes" : "no"}`,
    `- Automatic unblock: ${approvalReview.automatic_unblock ? "yes" : "no"}`,
    `- Reason: ${approvalReview.reason || "No approval review available."}`,
    "",
    "## PR Comment",
    "",
    workflow.pr_comment_markdown?.trim() || "No PR comment available."
  ];
  return `${lines.join("\n")}\n`;
}

export function buildGeneratedArtifactManifest(payload = {}, generatedArtifacts = [], options = {}) {
  const gate = payload.release_gate || {};
  const summary = payload.summary || {};
  const workflow = payload.release_workflow || {};
  const workspaceRoot = resolve(options.workspaceRoot || process.cwd());
  return {
    schema_version: "a3.generated_artifact_manifest.v1",
    generated_at: payload.generated_at || "runtime",
    source: payload.source || "local-fixtures",
    command_shape: payload.command_shape || "ashr gate --json",
    manifest_file: options.outputManifest
      ? portableArtifactPath(resolve(options.outputManifest), workspaceRoot)
      : null,
    manifest_self_hash: "excluded_to_avoid_self_reference",
    release: {
      run_id: summary.lastRunId || "unknown-run",
      decision: gate.decision || "unknown",
      decision_label: gate.decision_label || "unknown",
      risk_score: gate.risk_score ?? null,
      blocks_merge: Boolean(gate.pr_gate?.blocks_merge || (payload.trusted_release_authority && payload.trusted_release_authority.allowed !== true)),
      github_check_conclusion: payload.github_check_run?.conclusion || workflow.github_check?.conclusion || "unknown",
      decision_authority: payload.trusted_release_authority ? "A2 Decision Ledger" : "A3 triage summary only",
      a2_upstream_decision: payload.trusted_release_authority?.upstream_decision || "not-attached",
      a2_release_ready: payload.trusted_release_authority?.release_ready === true,
      a3_recomputed_a2_decision: false
    },
    redaction_policy: payload.audit_manifest?.redaction_policy
      || "No API keys, cookies, tokens, emails, or live signed media URLs are allowed in generated artifacts.",
    generated_artifacts: generatedArtifacts.map((artifact) => ({
      id: artifact.id,
      path: artifact.path,
      content_type: artifact.content_type,
      sha256: artifact.sha256,
      byte_size: artifact.byte_size,
      required: artifact.required !== false,
      ...(artifact.bundle_role ? { bundle_role: artifact.bundle_role } : {}),
      ...(artifact.origin ? { origin: artifact.origin } : {})
    })),
    safety: {
      dry_run_compatible: true,
      contains_secret_values: false,
      local_absolute_paths_allowed: false,
      manifest_hashes_itself: false
    }
  };
}

export function buildAuditBundleIndex(payload = {}, generatedArtifacts = [], options = {}) {
  const workspaceRoot = resolve(options.workspaceRoot || process.cwd());
  const gate = payload.release_gate || {};
  const workflow = payload.release_workflow || {};
  const summary = payload.summary || {};
  const releaseVersion = workflow.release_version || options.releaseVersion || "unknown-release";
  const generatedAt = payload.generated_at || options.generatedAt || "runtime";
  const bundleId = options.bundleId || buildBundleId(summary.lastRunId, releaseVersion, generatedAt);
  const sourceArtifacts = arrayOf(payload.audit_manifest?.artifacts).map((artifact) => normalizeBundleArtifact({
    ...artifact,
    bundle_role: ["waiver", "approval"].includes(artifact.id) ? "governance_record" : "source_input",
    created_by: "ashr gate input manifest"
  }, workspaceRoot));
  const outputArtifacts = arrayOf(generatedArtifacts).map((artifact) => {
    const isManifest = artifact.id === "generated_artifact_manifest";
    return normalizeBundleArtifact({
      ...artifact,
      bundle_role: artifact.bundle_role || (isManifest ? "custody_record" : "generated_output"),
      created_by: artifact.created_by || externalArtifactCreator(artifact, isManifest)
    }, workspaceRoot);
  });
  const bundleArtifacts = dedupeBundleArtifacts([...sourceArtifacts, ...outputArtifacts])
    .filter((artifact) => artifact.id !== "audit_bundle_index")
    .sort(compareBundleArtifacts);
  const chainOfCustody = buildChainOfCustodyEvents({
    payload,
    bundleId,
    bundleArtifacts,
    generatedAt,
    outputBundle: options.outputBundle,
    workspaceRoot
  });
  const indexWithoutRootHash = {
    schema_version: "a3.audit_bundle_index.v1",
    generated_at: generatedAt,
    source: payload.source || "local-fixtures",
    command_shape: payload.command_shape || "ashr gate --json",
    bundle_id: bundleId,
    bundle_index_file: options.outputBundle
      ? portableArtifactPath(resolve(options.outputBundle), workspaceRoot)
      : null,
    bundle_index_self_hash: "excluded_to_avoid_self_reference",
    root_hash_algorithm: "sha256",
    root_hash_input: "canonical_json_without_root_hash_or_bundle_index_file_bytes",
    release: {
      run_id: summary.lastRunId || "unknown-run",
      release_version: releaseVersion,
      environment: workflow.environment || options.environment || "unknown",
      owner: workflow.owner || options.owner || "unknown",
      decision: gate.decision || "unknown",
      decision_label: gate.decision_label || "unknown",
      risk_score: gate.risk_score ?? null,
      pass_rate: summary.passRate ?? null,
      average_score: summary.avgScore ?? null,
      blocks_merge: Boolean(gate.pr_gate?.blocks_merge || (payload.trusted_release_authority && payload.trusted_release_authority.allowed !== true)),
      github_check_conclusion: payload.github_check_run?.conclusion || workflow.github_check?.conclusion || "unknown",
      decision_authority: payload.trusted_release_authority ? "A2 Decision Ledger" : "A3 triage summary only",
      a2_integrity_verified: payload.trusted_release_authority?.integrity_verified === true,
      a2_upstream_decision: payload.trusted_release_authority?.upstream_decision || "not-attached",
      a2_release_ready: payload.trusted_release_authority?.release_ready === true,
      a2_decision_ledger_head_hash: payload.trusted_release_authority?.decision_ledger?.head_hash || null,
      a2_decision_record_id: payload.trusted_release_authority?.decision_ledger?.record_id || null,
      a3_recomputed_a2_decision: false,
      failed_checks: gate.failed_checks || []
    },
    governance: {
      waiver_status: payload.waiver_review?.status || "unknown",
      waiver_accepted: payload.waiver_review?.accepted === true,
      approval_status: payload.approval_review?.status || "unknown",
      approval_accepted: payload.approval_review?.accepted === true,
      automatic_unblock_allowed: false,
      required_approvers: gate.required_approvers || []
    },
    artifact_groups: {
      source_inputs: bundleArtifacts.filter((artifact) => artifact.bundle_role === "source_input").map((artifact) => artifact.id),
      generated_outputs: bundleArtifacts.filter((artifact) => artifact.bundle_role === "generated_output").map((artifact) => artifact.id),
      governance_records: bundleArtifacts.filter((artifact) => artifact.bundle_role === "governance_record").map((artifact) => artifact.id),
      custody_records: bundleArtifacts.filter((artifact) => artifact.bundle_role === "custody_record").map((artifact) => artifact.id),
      authority_records: bundleArtifacts.filter((artifact) => artifact.bundle_role === "authority_record").map((artifact) => artifact.id),
      readback_records: bundleArtifacts.filter((artifact) => artifact.bundle_role === "readback_record").map((artifact) => artifact.id),
      deployment_records: bundleArtifacts.filter((artifact) => artifact.bundle_role === "deployment_record").map((artifact) => artifact.id)
    },
    bundle_artifacts: bundleArtifacts,
    completeness: {
      status: bundleArtifacts.some((artifact) => artifact.required && !artifact.sha256) ? "partial" : "complete",
      required_artifact_count: bundleArtifacts.filter((artifact) => artifact.required).length,
      optional_artifact_count: bundleArtifacts.filter((artifact) => !artifact.required).length,
      missing_required_artifacts: bundleArtifacts
        .filter((artifact) => artifact.required && !artifact.sha256)
        .map((artifact) => artifact.id)
    },
    chain_of_custody: chainOfCustody,
    retention: {
      storage_backend: options.storageBackend || "local-filesystem",
      retention_days: Number(options.retentionDays || 30),
      legal_hold: false,
      immutable_write_once: true,
      verification_command: options.outputBundle
        ? `ashr gate verify --index ${portableArtifactPath(resolve(options.outputBundle), workspaceRoot)}`
        : "ashr gate verify --index <bundle-index.json>"
    },
    safety: {
      contains_secret_values: false,
      local_absolute_paths_allowed: false,
      self_hash_excluded: true,
      dry_run_compatible: true,
      redaction_policy: payload.audit_manifest?.redaction_policy
        || "No API keys, cookies, tokens, emails, or live signed media URLs are allowed in audit bundles."
    }
  };
  const { value: redactedIndex } = redactExport(indexWithoutRootHash, { surface: "audit_bundle_index" });
  const bundleRootHash = sha256Text(canonicalJson(redactedIndex));
  return {
    ...redactedIndex,
    bundle_root_hash: bundleRootHash
  };
}

export async function verifyAuditBundleIndex(indexPath, options = {}) {
  const workspaceRoot = resolve(options.workspaceRoot || process.cwd());
  const resolvedIndexPath = resolve(indexPath);
  const index = JSON.parse(await readFile(resolvedIndexPath, "utf8"));
  const findings = [];

  if (index.schema_version !== "a3.audit_bundle_index.v1") {
    findings.push(bundleFinding("schema_version", "blocking", "Bundle index schema_version must be a3.audit_bundle_index.v1."));
  }

  const { bundle_root_hash: expectedRootHash, ...indexWithoutRootHash } = index;
  const actualRootHash = sha256Text(canonicalJson(indexWithoutRootHash));
  if (!/^[a-f0-9]{64}$/.test(String(expectedRootHash || ""))) {
    findings.push(bundleFinding("bundle_root_hash_missing", "blocking", "Bundle index is missing a valid SHA-256 root hash."));
  } else if (actualRootHash !== expectedRootHash) {
    findings.push(bundleFinding("bundle_root_hash_mismatch", "blocking", "Bundle root hash does not match the canonical bundle index."));
  }

  const artifactResults = await Promise.all(arrayOf(index.bundle_artifacts).map((artifact) => verifyBundleArtifact(artifact, workspaceRoot)));
  for (const artifactResult of artifactResults) {
    if (artifactResult.status === "missing" || artifactResult.status === "hash_mismatch" || artifactResult.status === "byte_size_mismatch") {
      findings.push(bundleFinding(`artifact_${artifactResult.status}`, "blocking", `${artifactResult.id}: ${artifactResult.message}`));
    } else if (artifactResult.status === "skipped_outside_workspace") {
      findings.push(bundleFinding("artifact_outside_workspace", "warning", `${artifactResult.id}: ${artifactResult.message}`));
    }
  }

  const custodyResults = verifyCustodyChain(arrayOf(index.chain_of_custody));
  for (const custodyFinding of custodyResults.findings) {
    findings.push(custodyFinding);
  }

  const unsafePathArtifacts = artifactResults.filter((artifact) => artifact.path_is_absolute || artifact.path_includes_user_home);
  for (const artifact of unsafePathArtifacts) {
    findings.push(bundleFinding("unsafe_artifact_path", "blocking", `${artifact.id}: artifact path is not safe to share.`));
  }

  const blockingFindings = findings.filter((finding) => finding.severity === "blocking");
  const status = blockingFindings.length ? "failed" : "passed";
  const result = {
    schema_version: "a3.audit_bundle_verification.v1",
    verified_at: options.generatedAt || "runtime",
    index_path: portableArtifactPath(resolvedIndexPath, workspaceRoot),
    bundle_id: index.bundle_id || "unknown-bundle",
    status,
    root_hash: {
      expected: expectedRootHash || null,
      actual: actualRootHash,
      passed: actualRootHash === expectedRootHash
    },
    artifacts: {
      total: artifactResults.length,
      checked: artifactResults.filter((artifact) => artifact.status !== "skipped_outside_workspace").length,
      passed: artifactResults.filter((artifact) => artifact.status === "passed").length,
      skipped: artifactResults.filter((artifact) => artifact.status === "skipped_outside_workspace").length,
      failed: artifactResults.filter((artifact) => ["missing", "hash_mismatch", "byte_size_mismatch"].includes(artifact.status)).length,
      results: artifactResults
    },
    chain_of_custody: {
      total: custodyResults.results.length,
      passed: custodyResults.results.filter((event) => event.status === "passed").length,
      failed: custodyResults.results.filter((event) => event.status !== "passed").length,
      results: custodyResults.results
    },
    safety: {
      contains_secret_values: false,
      local_absolute_paths_allowed: false,
      unsafe_path_count: unsafePathArtifacts.length,
      self_hash_excluded: index.bundle_index_self_hash === "excluded_to_avoid_self_reference"
    },
    findings,
    process_exit_code: options.noFail ? 0 : status === "passed" ? 0 : 1
  };
  const { value } = redactExport(result, { surface: "audit_bundle_verification" });
  return value;
}

export function renderBundleVerificationMarkdown(verification = {}) {
  const lines = [
    "# Ashr++ Audit Bundle Verification",
    "",
    `- Bundle: ${verification.bundle_id || "unknown"}`,
    `- Status: ${verification.status || "unknown"}`,
    `- Root hash: ${verification.root_hash?.passed ? "passed" : "failed"}`,
    `- Artifacts: ${verification.artifacts?.passed || 0}/${verification.artifacts?.total || 0} passed`,
    `- Chain of custody: ${verification.chain_of_custody?.passed || 0}/${verification.chain_of_custody?.total || 0} passed`,
    `- Blocking findings: ${arrayOf(verification.findings).filter((finding) => finding.severity === "blocking").length}`,
    "",
    "## Findings",
    "",
    ...arrayOf(verification.findings).map((finding) => `- ${finding.severity}: ${finding.id} - ${finding.message}`),
    ""
  ];
  if (!arrayOf(verification.findings).length) {
    lines.splice(lines.length - 1, 0, "- No findings.");
  }
  return `${lines.join("\n")}\n`;
}

export function validateWaiverRequest(waiver = {}, gate = {}, workflow = {}, summary = {}, options = {}) {
  const policy = workflow.waiver_policy || {};
  const required = policy.required === true;
  const hasWaiver = waiver && typeof waiver === "object" && Object.keys(waiver).length > 0;
  const now = parseDateOrNull(options.generatedAt) || new Date();
  if (!hasWaiver) {
    return {
      schema_version: "a3.waiver_review.v1",
      available: false,
      status: required ? "missing_required_waiver" : "not_required",
      accepted: !required,
      automatic_unblock: false,
      reason: required
        ? "Release requires waiver evidence, but no waiver file was provided."
        : "Release does not require waiver evidence.",
      findings: required ? [waiverFinding("missing_waiver", "blocking", "No waiver file was provided.")] : []
    };
  }

  const findings = [];
  if (waiver.schema_version !== "a3.waiver.v1") {
    findings.push(waiverFinding("schema_version", "blocking", "Waiver schema_version must be a3.waiver.v1."));
  }
  for (const field of policy.required_fields || []) {
    if (isBlank(waiver[field])) {
      findings.push(waiverFinding(`missing_${field}`, "blocking", `Waiver is missing required field ${field}.`));
    }
  }

  const expectedRunId = summary.lastRunId || "";
  if (waiver.run_id && expectedRunId && waiver.run_id !== expectedRunId) {
    findings.push(waiverFinding("run_id_mismatch", "blocking", `Waiver run_id ${waiver.run_id} does not match gate run ${expectedRunId}.`));
  }
  if (waiver.release_version && options.releaseVersion && waiver.release_version !== options.releaseVersion) {
    findings.push(waiverFinding("release_version_mismatch", "blocking", "Waiver release_version does not match the gate release version."));
  }
  if (waiver.environment && options.environment && waiver.environment !== options.environment) {
    findings.push(waiverFinding("environment_mismatch", "blocking", "Waiver environment does not match the gate environment."));
  }
  if (waiver.head_sha && options.headSha && waiver.head_sha !== options.headSha) {
    findings.push(waiverFinding("head_sha_mismatch", "blocking", "Waiver head_sha does not match the gate head SHA."));
  }

  const expiry = parseDateOrNull(waiver.expiry_date);
  if (!expiry) {
    findings.push(waiverFinding("expiry_date_invalid", "blocking", "Waiver expiry_date must be a valid ISO date."));
  } else {
    if (expiry <= now) {
      findings.push(waiverFinding("expiry_date_expired", "blocking", "Waiver is expired."));
    }
    if (Number(policy.expiry_max_days) > 0) {
      const maxExpiry = new Date(now.getTime() + Number(policy.expiry_max_days) * 24 * 60 * 60 * 1000);
      if (expiry > maxExpiry) {
        findings.push(waiverFinding("expiry_date_too_late", "blocking", `Waiver expiry exceeds ${policy.expiry_max_days} day policy.`));
      }
    }
  }

  const requiredApprovers = workflow.reviewer_workflow?.required_approvers || gate.required_approvers || [];
  const approvedRoles = new Set(arrayOf(waiver.approved_by).map((item) => item.role).filter(Boolean));
  const missingApprovers = requiredApprovers.filter((role) => !approvedRoles.has(role));
  if (missingApprovers.length) {
    findings.push(waiverFinding("missing_required_approvers", "blocking", `Missing required approver role(s): ${missingApprovers.join(", ")}.`));
  }
  for (const approval of arrayOf(waiver.approved_by)) {
    if (isBlank(approval.role) || isBlank(approval.name) || !parseDateOrNull(approval.approved_at)) {
      findings.push(waiverFinding("approval_record_invalid", "blocking", "Each approval must include role, name, and valid approved_at."));
      break;
    }
  }

  const blockedChecks = new Set(arrayOf(waiver.blocked_checks));
  const missingChecks = (gate.failed_checks || []).filter((check) => !blockedChecks.has(check));
  if (missingChecks.length) {
    findings.push(waiverFinding("missing_blocked_checks", "blocking", `Waiver does not cover failed check(s): ${missingChecks.join(", ")}.`));
  }

  for (const artifact of arrayOf(waiver.reviewed_artifacts)) {
    if (!/^[a-f0-9]{64}$/.test(String(artifact.sha256 || ""))) {
      findings.push(waiverFinding("reviewed_artifact_hash_invalid", "blocking", "Reviewed artifact hashes must be SHA-256 hex strings."));
      break;
    }
  }

  const blockingFindings = findings.filter((finding) => finding.severity === "blocking");
  const exceptionalOnly = policy.exceptional_only === true;
  const accepted = required ? blockingFindings.length === 0 : false;
  const status = accepted
    ? exceptionalOnly ? "valid_exceptional_waiver" : "valid_waiver"
    : "invalid_waiver";

  return {
    schema_version: "a3.waiver_review.v1",
    available: true,
    status,
    accepted,
    automatic_unblock: false,
    automatic_unblock_reason: gate.decision === "block_release"
      ? "Blocked releases still require manual executive sign-off; a valid waiver is evidence, not an automatic unblock."
      : "Waiver validation records approval evidence but does not change CLI exit behavior in this local contract.",
    waiver: {
      waiver_id: waiver.waiver_id || "unknown-waiver",
      run_id: waiver.run_id || "",
      release_version: waiver.release_version || "",
      environment: waiver.environment || "",
      expiry_date: waiver.expiry_date || "",
      follow_up_issue: waiver.follow_up_issue || "",
      approved_role_count: approvedRoles.size,
      required_approvers: requiredApprovers,
      missing_approvers: missingApprovers,
      covered_failed_checks: [...blockedChecks].filter((check) => (gate.failed_checks || []).includes(check)),
      missing_failed_checks: missingChecks,
      reviewed_artifact_count: arrayOf(waiver.reviewed_artifacts).length
    },
    policy: {
      required,
      allowed: policy.allowed === true,
      exceptional_only: exceptionalOnly,
      expiry_max_days: policy.expiry_max_days || 0,
      required_fields: policy.required_fields || []
    },
    findings,
    reason: accepted
      ? "Waiver evidence satisfies the local A3 waiver policy."
      : "Waiver evidence does not satisfy the local A3 waiver policy."
  };
}

export function validateApprovalRecord(approval = {}, gate = {}, workflow = {}, summary = {}, options = {}) {
  const required = gate.decision !== "approve_release";
  const hasApproval = approval && typeof approval === "object" && Object.keys(approval).length > 0;
  if (!hasApproval) {
    return {
      schema_version: "a3.approval_review.v1",
      available: false,
      status: required ? "missing_required_approval" : "not_required",
      accepted: !required,
      automatic_unblock: false,
      reason: required
        ? "Release requires approval evidence, but no approval file was provided."
        : "Release does not require approval evidence.",
      findings: required ? [approvalFinding("missing_approval", "blocking", "No approval file was provided.")] : []
    };
  }

  const findings = [];
  if (approval.schema_version !== "a3.approval.v1") {
    findings.push(approvalFinding("schema_version", "blocking", "Approval schema_version must be a3.approval.v1."));
  }
  for (const field of ["approval_id", "decision", "run_id", "release_version", "environment"]) {
    if (isBlank(approval[field])) {
      findings.push(approvalFinding(`missing_${field}`, "blocking", `Approval is missing required field ${field}.`));
    }
  }

  const allowedDecisions = new Set(["approve_release", "approve_exception", "reject_release", "request_changes"]);
  if (!allowedDecisions.has(approval.decision)) {
    findings.push(approvalFinding("decision_invalid", "blocking", "Approval decision must be approve_release, approve_exception, reject_release, or request_changes."));
  }
  if (gate.decision === "block_release" && approval.decision === "approve_release") {
    findings.push(approvalFinding("decision_too_permissive", "blocking", "Blocked releases cannot be approved as normal releases."));
  }
  if (gate.decision !== "approve_release" && approval.decision !== "approve_exception") {
    findings.push(approvalFinding("exception_decision_required", "blocking", "Non-approved releases require approve_exception approval evidence."));
  }

  const expectedRunId = summary.lastRunId || "";
  if (approval.run_id && expectedRunId && approval.run_id !== expectedRunId) {
    findings.push(approvalFinding("run_id_mismatch", "blocking", `Approval run_id ${approval.run_id} does not match gate run ${expectedRunId}.`));
  }
  if (approval.release_version && options.releaseVersion && approval.release_version !== options.releaseVersion) {
    findings.push(approvalFinding("release_version_mismatch", "blocking", "Approval release_version does not match the gate release version."));
  }
  if (approval.environment && options.environment && approval.environment !== options.environment) {
    findings.push(approvalFinding("environment_mismatch", "blocking", "Approval environment does not match the gate environment."));
  }
  if (approval.head_sha && options.headSha && approval.head_sha !== options.headSha) {
    findings.push(approvalFinding("head_sha_mismatch", "blocking", "Approval head_sha does not match the gate head SHA."));
  }

  const waiver = options.waiver || {};
  const hasWaiverEvidence = waiver && typeof waiver === "object" && Object.keys(waiver).length > 0;
  if (gate.decision !== "approve_release" && !hasWaiverEvidence) {
    findings.push(approvalFinding("missing_waiver_evidence", "blocking", "Exception approvals must resolve a waiver record in the same tenant scope."));
  }
  if (approval.waiver_id && approval.waiver_id !== waiver.waiver_id) {
    findings.push(approvalFinding("waiver_id_mismatch", "blocking", "Approval waiver_id does not match the provided waiver."));
  }
  if (gate.decision !== "approve_release" && isBlank(approval.waiver_id)) {
    findings.push(approvalFinding("missing_waiver_id", "blocking", "Exception approvals must reference a waiver_id."));
  }

  const signer = approval.signer || {};
  if (isBlank(signer.role) || isBlank(signer.name) || !parseDateOrNull(signer.signed_at)) {
    findings.push(approvalFinding("signer_invalid", "blocking", "Approval signer must include role, name, and valid signed_at."));
  }

  const signerRoles = new Set([
    signer.role,
    ...arrayOf(approval.co_signers).map((item) => item.role)
  ].filter(Boolean));
  for (const coSigner of arrayOf(approval.co_signers)) {
    if (isBlank(coSigner.role) || isBlank(coSigner.name) || !parseDateOrNull(coSigner.signed_at)) {
      findings.push(approvalFinding("co_signer_invalid", "blocking", "Each co-signer must include role, name, and valid signed_at."));
      break;
    }
  }
  const requiredApprovers = workflow.reviewer_workflow?.required_approvers || gate.required_approvers || [];
  const missingApproverRoles = requiredApprovers.filter((role) => !signerRoles.has(role));
  if (missingApproverRoles.length) {
    findings.push(approvalFinding("missing_required_signer_roles", "blocking", `Approval is missing required signer role(s): ${missingApproverRoles.join(", ")}.`));
  }

  const reviewedArtifacts = arrayOf(approval.reviewed_artifacts);
  if (!reviewedArtifacts.length) {
    findings.push(approvalFinding("missing_reviewed_artifacts", "blocking", "Approval must include reviewed_artifacts."));
  }
  for (const artifact of reviewedArtifacts) {
    if (isBlank(artifact.id) || !/^[a-f0-9]{64}$/.test(String(artifact.sha256 || ""))) {
      findings.push(approvalFinding("reviewed_artifact_invalid", "blocking", "Reviewed artifacts must include id and SHA-256 hash."));
      break;
    }
  }

  if (approval.separation_of_duties?.release_author_is_signer === true) {
    findings.push(approvalFinding("separation_of_duties_failed", "blocking", "Release author cannot self-approve an exception."));
  }

  const blockingFindings = findings.filter((finding) => finding.severity === "blocking");
  const accepted = blockingFindings.length === 0 && approval.decision === (gate.decision === "approve_release" ? "approve_release" : "approve_exception");
  const status = accepted
    ? gate.decision === "approve_release" ? "valid_release_approval" : "valid_exception_approval"
    : "invalid_approval";

  return {
    schema_version: "a3.approval_review.v1",
    available: true,
    status,
    accepted,
    automatic_unblock: false,
    automatic_unblock_reason: "Approval evidence records sign-off, but this local contract does not change gate exit behavior.",
    approval: {
      approval_id: approval.approval_id || "unknown-approval",
      decision: approval.decision || "unknown",
      run_id: approval.run_id || "",
      release_version: approval.release_version || "",
      environment: approval.environment || "",
      head_sha: approval.head_sha || "",
      waiver_id: approval.waiver_id || "",
      signer_role: signer.role || "",
      signer_identity_source: signer.identity_source || "file",
      co_signer_count: arrayOf(approval.co_signers).length,
      reviewed_artifact_count: reviewedArtifacts.length,
      required_approvers: requiredApprovers,
      missing_required_signer_roles: missingApproverRoles
    },
    policy: {
      required,
      allowed_decisions: [...allowedDecisions],
      requires_waiver_reference: gate.decision !== "approve_release",
      separation_of_duties_required: true
    },
    findings,
    reason: accepted
      ? "Approval evidence satisfies the local A3 approval policy."
      : "Approval evidence does not satisfy the local A3 approval policy."
  };
}

async function main(argv = []) {
  const options = parseArgs(argv);
  if (options.verifyIndex) {
    const verification = await verifyAuditBundleIndex(options.verifyIndex, options);
    const jsonText = `${JSON.stringify(verification, null, 2)}\n`;
    const markdownText = renderBundleVerificationMarkdown(verification);
    if (options.outputJson) {
      await writeTextFile(resolve(options.outputJson), jsonText);
    }
    if (options.outputMarkdown) {
      await writeTextFile(resolve(options.outputMarkdown), markdownText);
    }
    if (options.format === "markdown") {
      process.stdout.write(markdownText);
    } else {
      process.stdout.write(jsonText);
    }
    return verification.process_exit_code;
  }
  const payload = await buildGateCliPayload(options);
  const jsonText = `${JSON.stringify(payload, null, 2)}\n`;
  const markdownText = renderGateCliMarkdown(payload);
  await writeRequestedOutputs(options, payload, jsonText, markdownText);
  if (options.format === "markdown") {
    process.stdout.write(markdownText);
  } else {
    process.stdout.write(jsonText);
  }
  return payload.process_exit_code;
}

function parseArgs(argv = []) {
  const options = {
    format: "json",
    source: "local-fixtures",
    environment: "staging",
    owner: "Release owner"
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = argv[index + 1];
    if (arg === "--runs") {
      options.runs = next;
      index += 1;
    } else if (arg === "--grades") {
      options.grades = next;
      index += 1;
    } else if (arg === "--coverage") {
      options.coverage = next;
      index += 1;
    } else if (arg === "--media-signed-url-coverage") {
      options.mediaSignedUrlCoverage = next;
      index += 1;
    } else if (arg === "--thresholds") {
      options.thresholds = next;
      index += 1;
    } else if (arg === "--waiver") {
      options.waiver = next;
      index += 1;
    } else if (arg === "--approval") {
      options.approval = next;
      index += 1;
    } else if (arg === "--a2-trusted-spine") {
      options.a2TrustedSpine = next;
      index += 1;
    } else if (arg === "--release-version") {
      options.releaseVersion = next;
      index += 1;
    } else if (arg === "--generated-at") {
      options.generatedAt = next;
      index += 1;
    } else if (arg === "--environment") {
      options.environment = next;
      index += 1;
    } else if (arg === "--owner") {
      options.owner = next;
      index += 1;
    } else if (arg === "--source") {
      options.source = next;
      index += 1;
    } else if (arg === "--format") {
      options.format = next;
      index += 1;
    } else if (arg === "--output-json") {
      options.outputJson = next;
      index += 1;
    } else if (arg === "--output-md") {
      options.outputMarkdown = next;
      index += 1;
    } else if (arg === "--output-check") {
      options.outputCheck = next;
      index += 1;
    } else if (arg === "--output-pr-comment") {
      options.outputPrComment = next;
      index += 1;
    } else if (arg === "--output-manifest") {
      options.outputManifest = next;
      index += 1;
    } else if (arg === "--output-bundle") {
      options.outputBundle = next;
      index += 1;
    } else if (arg === "--github-check-publish-receipt") {
      options.githubCheckPublishReceipt = next;
      index += 1;
    } else if (arg === "--github-pr-comment-publish-receipt") {
      options.githubPrCommentPublishReceipt = next;
      index += 1;
    } else if (arg === "--github-required-check-plan") {
      options.githubRequiredCheckPlan = next;
      index += 1;
    } else if (arg === "--github-check-readback") {
      options.githubCheckReadback = next;
      index += 1;
    } else if (arg === "--github-pr-comment-readback") {
      options.githubPrCommentReadback = next;
      index += 1;
    } else if (arg === "--github-required-check-proof") {
      options.githubRequiredCheckProof = next;
      index += 1;
    } else if (arg === "--deployment-probe") {
      options.deploymentProbe = next;
      index += 1;
    } else if (arg === "--verify-index") {
      options.verifyIndex = next;
      index += 1;
    } else if (arg === "--head-sha") {
      options.headSha = next;
      index += 1;
    } else if (arg === "--details-url") {
      options.detailsUrl = next;
      index += 1;
    } else if (arg === "--annotation-path") {
      options.annotationPath = next;
      index += 1;
    } else if (arg === "--json") {
      options.format = "json";
    } else if (arg === "--markdown") {
      options.format = "markdown";
    } else if (arg === "--strict-exit") {
      options.noFail = false;
    } else if (arg === "--no-fail") {
      options.noFail = true;
    } else if (arg === "--help" || arg === "-h") {
      options.help = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (options.help) {
    process.stdout.write(helpText());
    process.exit(0);
  }
  if (!options.verifyIndex && (!options.runs || !options.grades)) {
    throw new Error("--runs and --grades are required.");
  }
  if (!["json", "markdown"].includes(options.format)) {
    throw new Error("--format must be json or markdown.");
  }
  return options;
}

function helpText() {
  return `Usage: node services/report/a3_gate_cli.mjs --runs fixtures/a3/mock_run_results.json --grades fixtures/a3/mock_grade_results.json --coverage fixtures/a2/results/a2_g3_coverage_report.json --thresholds fixtures/a3/release_gate_thresholds.json --json [--a2-trusted-spine path] [--waiver path] [--approval path] [--generated-at ISO] [--strict-exit|--no-fail] [--output-json path] [--output-md path] [--output-check path] [--output-pr-comment path] [--output-manifest path] [--output-bundle path] [--github-check-publish-receipt path] [--github-pr-comment-publish-receipt path] [--github-required-check-plan path] [--github-check-readback path] [--github-pr-comment-readback path] [--github-required-check-proof path] [--deployment-probe path]\n       node services/report/a3_gate_cli.mjs --verify-index fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json --json [--output-json path] [--output-md path] [--strict-exit|--no-fail]\n`;
}

async function loadJsonRequired(path, label) {
  if (!path) {
    throw new Error(`${label} path is required.`);
  }
  return JSON.parse(await readFile(resolve(path), "utf8"));
}

async function loadJsonOptional(path) {
  if (!path) {
    return {};
  }
  return JSON.parse(await readFile(resolve(path), "utf8"));
}

function inputArtifact(id, path, required, workspaceRoot) {
  if (!path) {
    return null;
  }
  const resolvedPath = resolve(path);
  return {
    id,
    path: portableArtifactPath(resolvedPath, workspaceRoot),
    required,
    resolved_path: resolvedPath
  };
}

function portableArtifactPath(resolvedPath, workspaceRoot) {
  const relativePath = relative(workspaceRoot, resolvedPath);
  if (relativePath.startsWith("..") || isAbsolute(relativePath)) {
    return `[outside-workspace]/${basename(resolvedPath)}`;
  }
  return relativePath.replaceAll("\\", "/");
}

async function sha256File(path) {
  const bytes = await readFile(resolve(path));
  return createHash("sha256").update(bytes).digest("hex");
}

async function byteSizeFile(path) {
  return (await stat(resolve(path))).size;
}

function sha256Text(text) {
  return createHash("sha256").update(text).digest("hex");
}

function buildGithubCheckRunPayload(workflow = {}, gate = {}, summary = {}, options = {}) {
  const output = workflow.github_check?.output || {};
  const annotations = (gate.top_risk_cases || []).slice(0, 50).map((item) => ({
    path: options.annotationPath || "ashr-gate-report.md",
    start_line: 1,
    end_line: 1,
    annotation_level: gate.pr_gate?.blocks_merge ? "failure" : "warning",
    title: `${item.primary_failure_class}: ${item.case_id}`,
    message: `${item.title || item.case_id} scored ${item.score}; ${item.summary || "Review required."}`,
    raw_details: JSON.stringify({
      case_id: item.case_id,
      severity: item.severity,
      primary_failure_class: item.primary_failure_class,
      run_id: summary.lastRunId || null
    })
  }));
  return {
    name: workflow.github_check?.name || "Ashr++ Release Gate",
    head_sha: options.headSha || "[set-by-ci]",
    status: workflow.github_check?.status || "completed",
    conclusion: workflow.github_check?.conclusion || "neutral",
    details_url: options.detailsUrl || "",
    output: {
      title: output.title || `${gate.decision_label || "Release gate"}: ${summary.lastRunId || "unknown-run"}`,
      summary: output.summary || gate.summary || "Release gate completed.",
      text: output.text || "",
      annotations
    }
  };
}

async function writeRequestedOutputs(options = {}, payload = {}, jsonText = "", markdownText = "") {
  const workspaceRoot = resolve(options.workspaceRoot || process.cwd());
  const outputs = [
    outputArtifact("json_report", options.outputJson, jsonText, "application/json"),
    outputArtifact("markdown_report", options.outputMarkdown, markdownText, "text/markdown"),
    outputArtifact("github_check_run", options.outputCheck, `${JSON.stringify(payload.github_check_run, null, 2)}\n`, "application/json"),
    outputArtifact("pr_comment_markdown", options.outputPrComment, payload.pr_comment_markdown || "", "text/markdown")
  ].filter(Boolean);
  const generatedArtifacts = await Promise.all(outputs.map((artifact) => writeOutputArtifact(artifact, workspaceRoot)));
  const externalEvidenceArtifacts = await readExternalEvidenceArtifacts(options, workspaceRoot);
  const manifestInputs = [...generatedArtifacts, ...externalEvidenceArtifacts];
  let manifestArtifact = null;
  if (options.outputManifest) {
    const manifest = buildGeneratedArtifactManifest(payload, manifestInputs, {
      outputManifest: options.outputManifest,
      workspaceRoot
    });
    manifestArtifact = await writeOutputArtifact(
      outputArtifact(
        "generated_artifact_manifest",
        options.outputManifest,
        `${JSON.stringify(manifest, null, 2)}\n`,
        "application/json",
        false
      ),
      workspaceRoot
    );
  }
  if (options.outputBundle) {
    const bundleIndex = buildAuditBundleIndex(
      payload,
      manifestArtifact ? [...manifestInputs, manifestArtifact] : manifestInputs,
      {
        outputBundle: options.outputBundle,
        workspaceRoot,
        releaseVersion: options.releaseVersion,
        environment: options.environment,
        owner: options.owner
      }
    );
    await writeOutputArtifact(
      outputArtifact(
        "audit_bundle_index",
        options.outputBundle,
        `${JSON.stringify(bundleIndex, null, 2)}\n`,
        "application/json",
        true
      ),
      workspaceRoot
    );
  }
}

function outputArtifact(id, path, contents, contentType, required = true) {
  if (!path) {
    return null;
  }
  return {
    id,
    path,
    contents,
    content_type: contentType,
    required
  };
}

async function readExternalEvidenceArtifacts(options = {}, workspaceRoot) {
  const candidates = [
    externalEvidenceArtifactInput(
      "github_check_publish_receipt",
      options.githubCheckPublishReceipt,
      workspaceRoot,
      { origin: "external_github_publish_evidence", bundleRole: "generated_output" }
    ),
    externalEvidenceArtifactInput(
      "github_pr_comment_publish_receipt",
      options.githubPrCommentPublishReceipt,
      workspaceRoot,
      { origin: "external_github_publish_evidence", bundleRole: "generated_output" }
    ),
    externalEvidenceArtifactInput(
      "github_required_check_plan",
      options.githubRequiredCheckPlan,
      workspaceRoot,
      { origin: "external_github_publish_evidence", bundleRole: "generated_output" }
    ),
    externalEvidenceArtifactInput(
      "a2_trusted_spine",
      options.a2TrustedSpine,
      workspaceRoot,
      { origin: "a2_authoritative_evidence", bundleRole: "authority_record" }
    ),
    externalEvidenceArtifactInput(
      "github_check_readback",
      options.githubCheckReadback,
      workspaceRoot,
      { origin: "external_github_live_readback", bundleRole: "readback_record" }
    ),
    externalEvidenceArtifactInput(
      "github_pr_comment_readback",
      options.githubPrCommentReadback,
      workspaceRoot,
      { origin: "external_github_live_readback", bundleRole: "readback_record" }
    ),
    externalEvidenceArtifactInput(
      "github_required_check_proof",
      options.githubRequiredCheckProof,
      workspaceRoot,
      { origin: "external_github_live_readback", bundleRole: "readback_record" }
    ),
    externalEvidenceArtifactInput(
      "deployment_probe",
      options.deploymentProbe,
      workspaceRoot,
      { origin: "deployment_acceptance_input", bundleRole: "deployment_record" }
    )
  ].filter(Boolean);
  return Promise.all(candidates.map(readExternalEvidenceArtifact));
}

function externalEvidenceArtifactInput(id, path, workspaceRoot, options = {}) {
  if (!path) {
    return null;
  }
  const resolvedPath = resolve(path);
  return {
    id,
    path: portableArtifactPath(resolvedPath, workspaceRoot),
    resolved_path: resolvedPath,
    content_type: contentTypeForPath(path),
    required: true,
    origin: options.origin || "external_evidence",
    bundle_role: options.bundleRole || "generated_output"
  };
}

async function readExternalEvidenceArtifact(artifact) {
  return {
    id: artifact.id,
    path: artifact.path,
    content_type: artifact.content_type,
    required: artifact.required,
    origin: artifact.origin,
    bundle_role: artifact.bundle_role,
    sha256: await sha256File(artifact.resolved_path),
    byte_size: await byteSizeFile(artifact.resolved_path)
  };
}

function externalArtifactCreator(artifact, isManifest) {
  if (isManifest) return "ashr gate generated artifact manifest";
  if (artifact.origin === "external_github_publish_evidence") return "ashr gate external GitHub publish evidence reader";
  if (artifact.origin === "a2_authoritative_evidence") return "A2 trusted release authority reader";
  if (artifact.origin === "external_github_live_readback") return "A3 GitHub live readback observer";
  if (artifact.origin === "deployment_acceptance_input") return "A3 deployment acceptance probe reader";
  return "ashr gate output writer";
}

function waiverFinding(id, severity, message) {
  return { id, severity, message };
}

function approvalFinding(id, severity, message) {
  return { id, severity, message };
}

function bundleFinding(id, severity, message) {
  return { id, severity, message };
}

function arrayOf(value) {
  return Array.isArray(value) ? value : [];
}

function isBlank(value) {
  return typeof value !== "string" || value.trim() === "";
}

function parseDateOrNull(value) {
  if (!value || value === "runtime") {
    return null;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

async function writeOutputArtifact(artifact, workspaceRoot) {
  const resolvedPath = resolve(artifact.path);
  await writeTextFile(resolvedPath, artifact.contents);
  return {
    id: artifact.id,
    path: portableArtifactPath(resolvedPath, workspaceRoot),
    content_type: artifact.content_type,
    required: artifact.required,
    sha256: await sha256File(resolvedPath),
    byte_size: Buffer.byteLength(artifact.contents, "utf8")
  };
}

function normalizeBundleArtifact(artifact = {}, workspaceRoot) {
  const path = normalizePortablePath(artifact.path || "");
  return {
    id: artifact.id || "unknown_artifact",
    path,
    bundle_role: artifact.bundle_role || "generated_output",
    content_type: artifact.content_type || contentTypeForPath(path),
    required: artifact.required !== false,
    sha256: artifact.sha256 || null,
    byte_size: Number.isFinite(Number(artifact.byte_size)) ? Number(artifact.byte_size) : null,
    created_by: artifact.created_by || "ashr gate",
    ...(artifact.origin ? { origin: artifact.origin } : {}),
    redaction_status: "redacted_or_safe_for_audit"
  };
}

function normalizePortablePath(path = "") {
  const normalized = String(path).replaceAll("\\", "/");
  if (!normalized) {
    return "";
  }
  if (/^[A-Za-z]:\//.test(normalized) || normalized.startsWith("/")) {
    return `[outside-workspace]/${basename(normalized)}`;
  }
  return normalized;
}

function dedupeBundleArtifacts(artifacts = []) {
  const seen = new Set();
  const deduped = [];
  for (const artifact of artifacts) {
    const key = `${artifact.id}\n${artifact.path}`;
    if (!seen.has(key)) {
      seen.add(key);
      deduped.push(artifact);
    }
  }
  return deduped;
}

function compareBundleArtifacts(left, right) {
  return `${left.bundle_role}:${left.id}:${left.path}`.localeCompare(`${right.bundle_role}:${right.id}:${right.path}`);
}

function buildChainOfCustodyEvents({ payload = {}, bundleId, bundleArtifacts = [], generatedAt, outputBundle, workspaceRoot }) {
  const generatedArtifacts = bundleArtifacts
    .filter((artifact) => ["generated_output", "custody_record"].includes(artifact.bundle_role));
  const generatedArtifactIds = generatedArtifacts.map((artifact) => artifact.id);
  const hasExternalGithubEvidence = generatedArtifacts
    .some((artifact) => artifact.origin === "external_github_publish_evidence");
  const events = [
    custodyEvent("gate_built", "completed", ["runs", "grades"], "Release gate payload generated from source inputs."),
    custodyEvent("input_artifacts_hashed", "completed", bundleArtifacts
      .filter((artifact) => artifact.bundle_role === "source_input")
      .map((artifact) => artifact.id), "Source inputs hashed for audit manifest.")
  ];
  if (generatedArtifactIds.length) {
    events.push(custodyEvent(
      "generated_artifacts_hashed",
      "completed",
      generatedArtifactIds,
      hasExternalGithubEvidence
        ? "Generated report/check/comment and GitHub publish evidence artifacts hashed."
        : "Generated report/check/comment artifacts hashed."
    ));
  }
  const authorityArtifactIds = bundleArtifacts
    .filter((artifact) => artifact.bundle_role === "authority_record")
    .map((artifact) => artifact.id);
  if (authorityArtifactIds.length) {
    events.push(custodyEvent(
      "a2_authority_hashed",
      "completed",
      authorityArtifactIds,
      "A2 trusted release authority evidence hashed without recomputing its decision."
    ));
  }
  const readbackArtifactIds = bundleArtifacts
    .filter((artifact) => artifact.bundle_role === "readback_record")
    .map((artifact) => artifact.id);
  if (readbackArtifactIds.length) {
    events.push(custodyEvent(
      "github_readbacks_hashed",
      "completed",
      readbackArtifactIds,
      "Sanitized GitHub readback receipts hashed."
    ));
  }
  const deploymentArtifactIds = bundleArtifacts
    .filter((artifact) => artifact.bundle_role === "deployment_record")
    .map((artifact) => artifact.id);
  if (deploymentArtifactIds.length) {
    events.push(custodyEvent(
      "deployment_probe_hashed",
      "completed",
      deploymentArtifactIds,
      "Deployment acceptance probe evidence hashed."
    ));
  }
  if (payload.waiver_review?.available) {
    events.push(custodyEvent("waiver_reviewed", payload.waiver_review.accepted ? "accepted" : "rejected", ["waiver"], payload.waiver_review.reason || "Waiver review completed."));
  }
  if (payload.approval_review?.available) {
    events.push(custodyEvent("approval_reviewed", payload.approval_review.accepted ? "accepted" : "rejected", ["approval"], payload.approval_review.reason || "Approval review completed."));
  }
  events.push(custodyEvent(
    "bundle_index_written",
    "completed",
    ["audit_bundle_index"],
    outputBundle
      ? `Audit bundle index written to ${portableArtifactPath(resolve(outputBundle), workspaceRoot)}.`
      : "Audit bundle index built in memory."
  ));

  let previousEventHash = null;
  return events.map((event, index) => {
    const eventWithChain = {
      schema_version: "a3.custody_event.v1",
      event_id: `${String(index + 1).padStart(3, "0")}-${event.action}`,
      bundle_id: bundleId,
      occurred_at: generatedAt,
      actor: "local-a3-gate-cli",
      previous_event_hash: previousEventHash,
      ...event
    };
    const eventHash = sha256Text(canonicalJson(eventWithChain));
    previousEventHash = eventHash;
    return {
      ...eventWithChain,
      event_hash: eventHash
    };
  });
}

function custodyEvent(action, status, artifactIds, note) {
  return {
    action,
    status,
    artifact_ids: artifactIds,
    note
  };
}

function buildBundleId(runId = "unknown-run", releaseVersion = "unknown-release", generatedAt = "runtime") {
  const slug = slugify(`${releaseVersion}-${runId}`).slice(0, 48) || "local-release";
  const shortHash = sha256Text(`${releaseVersion}|${runId}|${generatedAt}`).slice(0, 12);
  return `a3-bundle-${slug}-${shortHash}`;
}

function slugify(value = "") {
  return String(value).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function contentTypeForPath(path = "") {
  const normalized = String(path).toLowerCase();
  if (normalized.endsWith(".md")) {
    return "text/markdown";
  }
  if (normalized.endsWith(".json")) {
    return "application/json";
  }
  if (normalized.endsWith(".yml") || normalized.endsWith(".yaml")) {
    return "text/yaml";
  }
  if (normalized.endsWith(".png")) {
    return "image/png";
  }
  if (normalized.endsWith(".pdf")) {
    return "application/pdf";
  }
  return "application/octet-stream";
}

async function verifyBundleArtifact(artifact = {}, workspaceRoot) {
  const id = artifact.id || "unknown_artifact";
  const path = normalizePortablePath(artifact.path || "");
  const pathIsOutsideWorkspace = path.startsWith("[outside-workspace]/");
  const pathIsAbsolute = /^[A-Za-z]:\//.test(path) || path.startsWith("/");
  const userHomeSegment = ["Users", ""].join("/");
  const driveUserHomeSegment = ["C:", "Users"].join("/");
  const pathIncludesUserHome = path.includes(userHomeSegment) || path.includes(driveUserHomeSegment);
  if (!path || pathIsOutsideWorkspace || pathIsAbsolute) {
    return {
      id,
      path,
      status: "skipped_outside_workspace",
      expected_sha256: artifact.sha256 || null,
      actual_sha256: null,
      expected_byte_size: artifact.byte_size ?? null,
      actual_byte_size: null,
      path_is_absolute: pathIsAbsolute,
      path_includes_user_home: pathIncludesUserHome,
      message: "Artifact path is outside the verifiable workspace."
    };
  }
  const resolvedPath = resolve(workspaceRoot, path);
  const portablePath = portableArtifactPath(resolvedPath, workspaceRoot);
  if (portablePath.startsWith("[outside-workspace]/")) {
    return {
      id,
      path,
      status: "skipped_outside_workspace",
      expected_sha256: artifact.sha256 || null,
      actual_sha256: null,
      expected_byte_size: artifact.byte_size ?? null,
      actual_byte_size: null,
      path_is_absolute: true,
      path_includes_user_home: pathIncludesUserHome,
      message: "Artifact resolves outside the workspace."
    };
  }
  try {
    const bytes = await readFile(resolvedPath);
    const actualSha256 = sha256Text(bytes);
    const actualByteSize = bytes.length;
    const expectedSha256 = artifact.sha256 || "";
    if (actualSha256 !== expectedSha256) {
      return {
        id,
        path,
        status: "hash_mismatch",
        expected_sha256: expectedSha256,
        actual_sha256: actualSha256,
        expected_byte_size: artifact.byte_size ?? null,
        actual_byte_size: actualByteSize,
        path_is_absolute: false,
        path_includes_user_home: pathIncludesUserHome,
        message: "Artifact SHA-256 does not match bundle index."
      };
    }
    if (Number.isFinite(Number(artifact.byte_size)) && actualByteSize !== Number(artifact.byte_size)) {
      return {
        id,
        path,
        status: "byte_size_mismatch",
        expected_sha256: expectedSha256,
        actual_sha256: actualSha256,
        expected_byte_size: Number(artifact.byte_size),
        actual_byte_size: actualByteSize,
        path_is_absolute: false,
        path_includes_user_home: pathIncludesUserHome,
        message: "Artifact byte size does not match bundle index."
      };
    }
    return {
      id,
      path,
      status: "passed",
      expected_sha256: expectedSha256,
      actual_sha256: actualSha256,
      expected_byte_size: artifact.byte_size ?? null,
      actual_byte_size: actualByteSize,
      path_is_absolute: false,
      path_includes_user_home: pathIncludesUserHome,
      message: "Artifact hash and byte size match."
    };
  } catch {
    return {
      id,
      path,
      status: "missing",
      expected_sha256: artifact.sha256 || null,
      actual_sha256: null,
      expected_byte_size: artifact.byte_size ?? null,
      actual_byte_size: null,
      path_is_absolute: false,
      path_includes_user_home: pathIncludesUserHome,
      message: "Artifact file is missing or unreadable."
    };
  }
}

function verifyCustodyChain(events = []) {
  const findings = [];
  let previousEventHash = null;
  const results = events.map((event = {}, index) => {
    const { event_hash: expectedEventHash, ...eventWithoutHash } = event;
    const actualEventHash = sha256Text(canonicalJson(eventWithoutHash));
    const expectedPreviousHash = index === 0 ? null : previousEventHash;
    const previousHashPassed = event.previous_event_hash === expectedPreviousHash;
    const eventHashPassed = actualEventHash === expectedEventHash;
    const status = previousHashPassed && eventHashPassed ? "passed" : "failed";
    if (!previousHashPassed) {
      findings.push(bundleFinding("custody_previous_hash_mismatch", "blocking", `${event.event_id || index}: previous_event_hash does not match the prior event.`));
    }
    if (!eventHashPassed) {
      findings.push(bundleFinding("custody_event_hash_mismatch", "blocking", `${event.event_id || index}: event_hash does not match canonical event data.`));
    }
    previousEventHash = expectedEventHash || actualEventHash;
    return {
      event_id: event.event_id || `${index}`,
      action: event.action || "unknown",
      status,
      expected_event_hash: expectedEventHash || null,
      actual_event_hash: actualEventHash,
      previous_hash_passed: previousHashPassed,
      event_hash_passed: eventHashPassed
    };
  });
  return { results, findings };
}

function canonicalJson(value) {
  return JSON.stringify(canonicalizeValue(value));
}

function canonicalizeValue(value) {
  if (Array.isArray(value)) {
    return value.map(canonicalizeValue);
  }
  if (value && typeof value === "object") {
    return Object.keys(value).sort().reduce((object, key) => {
      object[key] = canonicalizeValue(value[key]);
      return object;
    }, {});
  }
  return value;
}

async function writeTextFile(path, contents) {
  const resolvedPath = resolve(path);
  await mkdir(dirname(resolvedPath), { recursive: true });
  await writeFile(resolvedPath, contents, "utf8");
}

const isDirectRun = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isDirectRun) {
  main(process.argv.slice(2)).then((exitCode) => {
    process.exitCode = exitCode;
  }).catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 2;
  });
}
