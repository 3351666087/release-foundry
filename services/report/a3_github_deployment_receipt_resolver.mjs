import { createHash } from "node:crypto";

import {
  A3_DEPLOYMENT_RECEIPT_AUTHORITATIVE_READBACK_SCHEMA_VERSION,
  deploymentReceiptDefinition
} from "./a3_deployment_receipt_workflow.mjs";
import {
  buildBranchProtectionRequiredCheckPlan,
  readGitHubCheckRun,
  readGitHubRepositoryInstallation,
  readRequiredCheckProof
} from "./a3_github_integration.mjs";

export const A3_GITHUB_DEPLOYMENT_EVIDENCE_SCHEMA_VERSION = "a3.github_deployment_evidence.v1";
export const A3_GITHUB_DEPLOYMENT_RECEIPT_OBSERVATION_SCHEMA_VERSION = "a3.github_deployment_receipt_observation.v1";

const SUPPORTED_BLOCKERS = new Set(["github_app_installation", "required_check_enforcement"]);
const SCOPE_FIELDS = ["organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"];

export function createA3GitHubDeploymentReceiptResolver(options = {}) {
  const fixedOptions = normalizeResolverOptions(options);
  return async function resolveGitHubDeploymentReceipt(input = {}) {
    const observation = await observeA3GitHubDeploymentReceipt(input, fixedOptions);
    if (typeof options.recordObservation === "function") {
      await options.recordObservation(structuredClone(observation));
    }
    return observation.authoritative_readback_input;
  };
}

export async function captureA3GitHubDeploymentEvidence(blockerId, options = {}) {
  const config = normalizeResolverOptions(options);
  if (!SUPPORTED_BLOCKERS.has(blockerId)) {
    throw new Error(`Unsupported GitHub deployment blocker: ${blockerId || "missing"}.`);
  }
  const captured = blockerId === "github_app_installation"
    ? await captureGitHubAppEvidence(config)
    : await captureRequiredCheckEvidence(config);
  const evidenceSha256 = `sha256:${sha256(stableJson(captured.canonical_evidence))}`;
  return {
    schema_version: A3_GITHUB_DEPLOYMENT_EVIDENCE_SCHEMA_VERSION,
    blocker_id: blockerId,
    provider: "github",
    target: publicTarget(config),
    captured_at: config.checkedAt,
    evidence_sha256: evidenceSha256,
    claims: captured.claims,
    canonical_evidence: captured.canonical_evidence,
    provider_readbacks: captured.provider_readbacks,
    authority_receipts: captured.authority_receipts,
    safety: {
      target_from_client: false,
      target_server_fixed: true,
      token_included: false,
      token_printed: false,
      raw_response_stored: false,
      mutation_performed: false,
      branch_protection_mutation_performed: false,
      merge_attempt_performed: false,
      secret_values_allowed: false
    }
  };
}

export async function observeA3GitHubDeploymentReceipt(input = {}, options = {}) {
  const receipt = input.receipt || {};
  const blockerId = String(receipt.blocker_id || "");
  const config = normalizeResolverOptions(options);
  if (!SUPPORTED_BLOCKERS.has(blockerId)) {
    throw new Error(`Unsupported GitHub deployment blocker: ${blockerId || "missing"}.`);
  }
  const evidence = await captureA3GitHubDeploymentEvidence(blockerId, config);
  const receiptScope = normalizeScope(receipt.tenant_scope || receipt);
  const scopeMatches = scopeComplete(receiptScope) && scopesEqual(receiptScope, config.expectedTenantScope);
  const candidateMatches = receipt.candidate_id === config.expectedCandidateId;
  const runMatches = receipt.run_id === config.expectedRunId;
  const evidenceHashMatches = receipt.evidence_sha256 === evidence.evidence_sha256;
  const claims = Object.fromEntries(Object.entries(evidence.claims)
    .map(([claim, passed]) => [claim, Boolean(passed && scopeMatches && candidateMatches && runMatches)]));
  const claimsPass = Object.values(claims).every((value) => value === true);
  const verificationStatus = scopeMatches && candidateMatches && runMatches && evidenceHashMatches && claimsPass
    ? "verified"
    : "rejected";
  const reasonCode = !scopeMatches
    ? "wrong_scope"
    : !candidateMatches || !runMatches
      ? "wrong_candidate"
      : !evidenceHashMatches
        ? "hash_mismatch"
        : "policy_not_satisfied";
  const definition = deploymentReceiptDefinition(blockerId);
  const attestationCore = {
    blocker_id: blockerId,
    receipt_id: receipt.receipt_id,
    candidate_id: receipt.candidate_id,
    run_id: receipt.run_id,
    tenant_scope: receiptScope,
    expected_evidence_sha256: receipt.evidence_sha256,
    observed_evidence_sha256: evidence.evidence_sha256,
    verifier_authority: definition?.verifier_authority,
    verification_status: verificationStatus,
    reason_code: verificationStatus === "verified" ? "all_bindings_verified" : reasonCode,
    claims
  };
  const authoritativeReadbackInput = {
    schema_version: A3_DEPLOYMENT_RECEIPT_AUTHORITATIVE_READBACK_SCHEMA_VERSION,
    external_readback_id_alias: `ghdpr_${sha256(stableJson(attestationCore)).slice(0, 20)}`,
    receipt_id: receipt.receipt_id,
    blocker_id: blockerId,
    candidate_id: receipt.candidate_id,
    run_id: receipt.run_id,
    tenant_scope: receiptScope,
    evidence_sha256: receipt.evidence_sha256,
    verifier_class: receipt.verifier_class,
    verifier_authority: definition?.verifier_authority,
    verification_status: verificationStatus,
    reason_code: verificationStatus === "verified" ? "all_bindings_verified" : reasonCode,
    verified_at: config.verifiedAt,
    attestation_sha256: `sha256:${sha256(stableJson(attestationCore))}`,
    claims
  };
  return {
    schema_version: A3_GITHUB_DEPLOYMENT_RECEIPT_OBSERVATION_SCHEMA_VERSION,
    blocker_id: blockerId,
    provider: "github",
    target: publicTarget(config),
    receipt_binding: {
      receipt_id_present: Boolean(receipt.receipt_id),
      candidate_matches: candidateMatches,
      run_matches: runMatches,
      tenant_scope_matches: scopeMatches,
      evidence_hash_matches: evidenceHashMatches,
      all_claims_pass: claimsPass
    },
    evidence,
    authoritative_readback_input: authoritativeReadbackInput,
    production_verified: verificationStatus === "verified",
    safety: {
      target_from_client: false,
      client_supplied_verification_result_used: false,
      browser_callable: false,
      token_included: false,
      raw_response_stored: false,
      mutation_performed: false,
      a2_decision_recomputed: false,
      source_acceptance_mutated: false
    }
  };
}

async function captureGitHubAppEvidence(config) {
  if (!config.checkRunId) throw new Error("checkRunId is required for GitHub App identity verification.");
  if (!config.expectedAppSlug) throw new Error("expectedAppSlug is required for GitHub App identity verification.");
  const publishReceipt = {
    schema_version: "a3.github_check_publish_receipt.v1",
    posted: true,
    dry_run: false,
    request: {
      repo: config.repoObject,
      body: {
        name: config.checkName,
        head_sha: config.headSha,
        conclusion: config.checkConclusion
      }
    },
    check_run: { id: config.checkRunId }
  };
  const common = githubReadOptions(config);
  const [installation, check] = await Promise.all([
    readGitHubRepositoryInstallation({
      ...common,
      repo: config.repo,
      expectedAppSlug: config.expectedAppSlug,
      expectedAppId: config.expectedAppId,
      expectedInstallationAlias: config.expectedInstallationAlias
    }),
    readGitHubCheckRun(publishReceipt, {
      ...common,
      repo: config.repo,
      checkRunId: config.checkRunId,
      checkName: config.checkName,
      headSha: config.headSha,
      conclusion: config.checkConclusion,
      skipOutputHash: true
    })
  ]);
  const tenantBinding = validateTenantInstallationBinding(config.tenantInstallationBinding, config, installation);
  const repositoryBound = installation.repository_bound === true;
  const checkIdentityVerified = check.readback_status === "readback_confirmed"
    && check.matches?.name !== false
    && check.matches?.head_sha !== false
    && check.observed?.app_slug === config.expectedAppSlug
    && (!config.expectedAppId || Number(check.observed?.app_id_alias) === config.expectedAppId);
  const claims = {
    tenant_installation_bound: tenantBinding.valid,
    repository_bound: repositoryBound,
    check_identity_verified: checkIdentityVerified
  };
  return {
    claims,
    canonical_evidence: {
      blocker_id: "github_app_installation",
      target: publicTarget(config),
      installation: stableInstallationEvidence(installation),
      check: stableCheckEvidence(check),
      tenant_binding: tenantBinding
    },
    provider_readbacks: { installation, check },
    authority_receipts: { tenant_installation_binding: tenantBinding }
  };
}

async function captureRequiredCheckEvidence(config) {
  const plan = buildBranchProtectionRequiredCheckPlan({
    repo: config.repo,
    branch: config.branch,
    checkName: config.checkName
  });
  const proof = await readRequiredCheckProof(plan, {
    ...githubReadOptions(config),
    repo: config.repo,
    branch: config.branch,
    checkName: config.checkName
  });
  const failingMergeDenial = validateRepositoryAuthorityReceipt(
    config.failingMergeDenialReceipt,
    "a3.github_failing_merge_denial_receipt.v1",
    config,
    (value) => value.denied === true && value.candidate_id === config.expectedCandidateId
  );
  const maintainerApproval = validateRepositoryAuthorityReceipt(
    config.maintainerApprovalReceipt,
    "a3.github_required_check_approval_receipt.v1",
    config,
    (value) => value.approved === true
  );
  const claims = {
    required_context_enforced: proof.enforced === true && proof.readback_status === "readback_confirmed",
    failing_merge_denied: failingMergeDenial.valid,
    maintainer_readback_verified: maintainerApproval.valid
  };
  return {
    claims,
    canonical_evidence: {
      blocker_id: "required_check_enforcement",
      target: publicTarget(config),
      required_check: stableRequiredCheckEvidence(proof),
      failing_merge_denial: failingMergeDenial,
      maintainer_approval: maintainerApproval
    },
    provider_readbacks: { required_check: proof },
    authority_receipts: { failing_merge_denial: failingMergeDenial, maintainer_approval: maintainerApproval }
  };
}

function normalizeResolverOptions(options = {}) {
  const repoObject = normalizeRepo(options.repo);
  if (!repoObject.owner || !repoObject.repo) throw new Error("A server-fixed repo in owner/name form is required.");
  const branch = safeIdentifier(options.branch || "main", "branch");
  const checkName = safeText(options.checkName || "A3 golden path release artifact", 180, "checkName");
  const expectedTenantScope = normalizeScope(options.expectedTenantScope || options.tenantScope);
  if (!scopeComplete(expectedTenantScope)) throw new Error("A complete server-fixed five-level tenant scope is required.");
  const expectedCandidateId = safeIdentifier(options.expectedCandidateId || options.candidateId, "expectedCandidateId");
  const expectedRunId = safeIdentifier(options.expectedRunId || options.runId, "expectedRunId");
  const checkedAt = validTimestamp(options.checkedAt) ? new Date(options.checkedAt).toISOString() : new Date().toISOString();
  const verifiedAt = validTimestamp(options.verifiedAt) ? new Date(options.verifiedAt).toISOString() : checkedAt;
  return {
    repo: `${repoObject.owner}/${repoObject.repo}`,
    repoObject,
    branch,
    checkName,
    checkRunId: positiveInteger(options.checkRunId),
    headSha: safeIdentifier(options.headSha || expectedCandidateId, "headSha"),
    checkConclusion: safeIdentifier(options.checkConclusion || "success", "checkConclusion"),
    expectedAppSlug: options.expectedAppSlug ? safeIdentifier(options.expectedAppSlug, "expectedAppSlug") : null,
    expectedAppId: positiveInteger(options.expectedAppId),
    expectedInstallationAlias: options.expectedInstallationAlias ? safeIdentifier(options.expectedInstallationAlias, "expectedInstallationAlias") : null,
    expectedTenantScope,
    expectedCandidateId,
    expectedRunId,
    tenantInstallationBinding: options.tenantInstallationBinding || null,
    failingMergeDenialReceipt: options.failingMergeDenialReceipt || null,
    maintainerApprovalReceipt: options.maintainerApprovalReceipt || null,
    token: options.token,
    tokenEnvName: options.tokenEnvName || "GITHUB_TOKEN",
    fetchImpl: options.fetchImpl,
    apiBaseUrl: options.apiBaseUrl,
    trustedApiOrigins: options.trustedApiOrigins,
    githubApiVersion: options.githubApiVersion,
    checkedAt,
    verifiedAt
  };
}

function githubReadOptions(config) {
  return {
    dryRun: false,
    token: config.token,
    tokenEnvName: config.tokenEnvName,
    fetchImpl: config.fetchImpl,
    apiBaseUrl: config.apiBaseUrl,
    trustedApiOrigins: config.trustedApiOrigins,
    githubApiVersion: config.githubApiVersion,
    checkedAt: config.checkedAt
  };
}

function validateTenantInstallationBinding(value, config, installation) {
  const integrity = validateHashedRecord(value, "a1.github_tenant_installation_binding.v1");
  const scope = normalizeScope(value?.tenant_scope || value || {});
  const valid = integrity.valid
    && value.authority === "a1_github_installation_service"
    && value.binding_status === "bound"
    && value.repo === config.repo
    && value.app_slug === config.expectedAppSlug
    && String(value.installation_alias || "") === String(installation.observed?.installation_id_alias || "")
    && scopesEqual(scope, config.expectedTenantScope);
  return {
    valid,
    schema_version: value?.schema_version || null,
    authority: value?.authority || null,
    binding_status: value?.binding_status || "missing",
    binding_id_alias: value?.binding_id_alias || null,
    record_hash: integrity.record_hash,
    scope_matches: scopeComplete(scope) && scopesEqual(scope, config.expectedTenantScope),
    repo_matches: value?.repo === config.repo,
    app_matches: value?.app_slug === config.expectedAppSlug,
    installation_matches: String(value?.installation_alias || "") === String(installation.observed?.installation_id_alias || ""),
    raw_identity_stored: false
  };
}

function validateRepositoryAuthorityReceipt(value, schemaVersion, config, predicate) {
  const integrity = validateHashedRecord(value, schemaVersion);
  const valid = integrity.valid
    && value.authority === "github_repository_policy_service"
    && value.repo === config.repo
    && value.branch === config.branch
    && value.required_check_context === config.checkName
    && scopesEqual(normalizeScope(value.tenant_scope || value), config.expectedTenantScope)
    && predicate(value);
  return {
    valid,
    schema_version: value?.schema_version || null,
    authority: value?.authority || null,
    receipt_id_alias: value?.receipt_id_alias || null,
    record_hash: integrity.record_hash,
    repo_matches: value?.repo === config.repo,
    branch_matches: value?.branch === config.branch,
    context_matches: value?.required_check_context === config.checkName,
    scope_matches: scopesEqual(normalizeScope(value?.tenant_scope || value || {}), config.expectedTenantScope),
    raw_identity_stored: false
  };
}

function validateHashedRecord(value, schemaVersion) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return { valid: false, record_hash: null };
  const { record_hash: recordHash, ...core } = value;
  const expected = `sha256:${sha256(stableJson(core))}`;
  return {
    valid: value.schema_version === schemaVersion && recordHash === expected,
    record_hash: typeof recordHash === "string" ? recordHash : null
  };
}

function stableInstallationEvidence(value = {}) {
  return {
    readback_status: value.readback_status || "missing",
    http_status: value.http_status ?? null,
    repository_bound: value.repository_bound === true,
    identity_matches: value.identity_matches === true,
    expected: value.expected || {},
    observed: value.observed || {},
    matches: value.matches || {},
    sanitized_error_class: value.sanitized_error_class || null
  };
}

function stableCheckEvidence(value = {}) {
  return {
    readback_status: value.readback_status || "missing",
    http_status: value.http_status ?? null,
    expected: value.expected || {},
    observed: {
      check_run_id_alias: value.observed?.check_run_id_alias || null,
      check_name: value.observed?.check_name || null,
      status: value.observed?.status || null,
      conclusion: value.observed?.conclusion || null,
      head_sha_alias: value.observed?.head_sha_alias || null,
      app_id_alias: value.observed?.app_id_alias || null,
      app_slug: value.observed?.app_slug || null,
      app_owner_type: value.observed?.app_owner_type || null
    },
    matches: value.matches || {},
    sanitized_error_class: value.sanitized_error_class || null
  };
}

function stableRequiredCheckEvidence(value = {}) {
  return {
    readback_status: value.readback_status || "missing",
    enforced: value.enforced === true,
    strict: value.strict === true,
    http_status: value.http_status ?? null,
    repo: value.repo || {},
    branch: value.branch || null,
    check_name: value.check_name || null,
    matched_check: value.matched_check || null,
    matched_context: value.matched_context || null,
    checked_count: Number(value.checked_count || 0),
    sanitized_error_class: value.sanitized_error_class || null
  };
}

function publicTarget(config) {
  return {
    repo: config.repo,
    branch: config.branch,
    check_name: config.checkName,
    check_run_id_alias: config.checkRunId,
    head_sha_alias: config.headSha,
    expected_app_slug: config.expectedAppSlug,
    expected_app_id_alias: config.expectedAppId,
    expected_installation_alias: config.expectedInstallationAlias,
    tenant_scope: config.expectedTenantScope,
    candidate_id: config.expectedCandidateId,
    run_id: config.expectedRunId
  };
}

function normalizeRepo(value) {
  const match = String(value || "").match(/^([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+)$/);
  return match ? { owner: match[1], repo: match[2] } : { owner: null, repo: null };
}

function normalizeScope(value = {}) {
  const nested = value.tenant_scope || value.tenantScope || {};
  return {
    organization_id: String(value.organization_id ?? value.organizationId ?? nested.organization_id ?? ""),
    tenant_id: String(value.tenant_id ?? value.tenantId ?? nested.tenant_id ?? ""),
    workspace_id: String(value.workspace_id ?? value.workspaceId ?? nested.workspace_id ?? ""),
    project_id: String(value.project_id ?? value.projectId ?? nested.project_id ?? ""),
    environment_id: String(value.environment_id ?? value.environmentId ?? nested.environment_id ?? "")
  };
}

function scopeComplete(value) {
  return SCOPE_FIELDS.every((field) => typeof value?.[field] === "string" && value[field].length > 0);
}

function scopesEqual(left, right) {
  return SCOPE_FIELDS.every((field) => left?.[field] === right?.[field]);
}

function safeIdentifier(value, field) {
  const normalized = String(value || "");
  if (!normalized || normalized.length > 240 || !/^[A-Za-z0-9._:/-]+$/.test(normalized)) {
    throw new Error(`${field} must be a safe opaque identifier.`);
  }
  return normalized;
}

function safeText(value, maximum, field) {
  const normalized = String(value || "").trim();
  if (!normalized || normalized.length > maximum || /[\r\n]/.test(normalized)) {
    throw new Error(`${field} is invalid.`);
  }
  return normalized;
}

function positiveInteger(value) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function validTimestamp(value) {
  return typeof value === "string" && value.length > 0 && Number.isFinite(Date.parse(value));
}

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function sha256(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}
