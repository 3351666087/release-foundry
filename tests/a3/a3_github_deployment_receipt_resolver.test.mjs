import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  captureA3GitHubDeploymentEvidence,
  createA3GitHubDeploymentReceiptResolver,
  observeA3GitHubDeploymentReceipt
} from "../../services/report/a3_github_deployment_receipt_resolver.mjs";

const TENANT_SCOPE = Object.freeze({
  organization_id: "org_acme",
  tenant_id: "tenant_refunds",
  workspace_id: "workspace_eval",
  project_id: "project_refund_agent",
  environment_id: "environment_staging"
});

const FIXED = Object.freeze({
  repo: "acme/refund-agent",
  branch: "main",
  checkName: "Ashr++ Release Gate",
  checkRunId: 9001,
  headSha: "candidate-abc123",
  checkConclusion: "success",
  expectedAppSlug: "ashr-enterprise",
  expectedAppId: 12345,
  expectedInstallationAlias: "7001",
  expectedTenantScope: TENANT_SCOPE,
  expectedCandidateId: "candidate-abc123",
  expectedRunId: "run-refund-001",
  token: "rt_secret",
  checkedAt: "2026-07-13T01:00:00Z",
  verifiedAt: "2026-07-13T01:00:01Z"
});

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function hashedRecord(core) {
  return {
    ...core,
    record_hash: `sha256:${createHash("sha256").update(stableJson(core)).digest("hex")}`
  };
}

function tenantInstallationBinding(overrides = {}) {
  return hashedRecord({
    schema_version: "a1.github_tenant_installation_binding.v1",
    authority: "a1_github_installation_service",
    binding_status: "bound",
    binding_id_alias: "binding-001",
    repo: FIXED.repo,
    app_slug: FIXED.expectedAppSlug,
    installation_alias: FIXED.expectedInstallationAlias,
    tenant_scope: TENANT_SCOPE,
    ...overrides
  });
}

function failingMergeDenialReceipt(overrides = {}) {
  return hashedRecord({
    schema_version: "a3.github_failing_merge_denial_receipt.v1",
    authority: "github_repository_policy_service",
    receipt_id_alias: "merge-denial-001",
    repo: FIXED.repo,
    branch: FIXED.branch,
    required_check_context: FIXED.checkName,
    tenant_scope: TENANT_SCOPE,
    denied: true,
    candidate_id: FIXED.expectedCandidateId,
    ...overrides
  });
}

function maintainerApprovalReceipt(overrides = {}) {
  return hashedRecord({
    schema_version: "a3.github_required_check_approval_receipt.v1",
    authority: "github_repository_policy_service",
    receipt_id_alias: "maintainer-approval-001",
    repo: FIXED.repo,
    branch: FIXED.branch,
    required_check_context: FIXED.checkName,
    tenant_scope: TENANT_SCOPE,
    approved: true,
    ...overrides
  });
}

function githubFetch(options = {}) {
  const appSlug = options.appSlug || FIXED.expectedAppSlug;
  const appId = options.appId || FIXED.expectedAppId;
  const installationStatus = options.installationStatus || 200;
  const checkStatus = options.checkStatus || 200;
  const protectionStatus = options.protectionStatus || 200;
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    if (url.endsWith("/installation")) {
      return new Response(JSON.stringify(installationStatus === 200 ? {
        id: 7001,
        app_id: appId,
        app_slug: appSlug,
        target_type: "Organization",
        repository_selection: "selected",
        permissions: { checks: "write", contents: "read" },
        events: ["check_run", "pull_request"],
        suspended_at: null,
        account: { login: "private-owner", email: "owner@example.com" }
      } : { message: "Not Found for owner@example.com" }), { status: installationStatus });
    }
    if (url.includes("/check-runs/")) {
      return new Response(JSON.stringify(checkStatus === 200 ? {
        id: FIXED.checkRunId,
        name: FIXED.checkName,
        status: "completed",
        conclusion: FIXED.checkConclusion,
        head_sha: FIXED.headSha,
        app: { id: appId, slug: appSlug, owner: { type: "Organization", login: "private-owner" } }
      } : { message: "Check unavailable" }), { status: checkStatus });
    }
    if (url.includes("/protection/required_status_checks")) {
      return new Response(JSON.stringify(protectionStatus === 200 ? {
        strict: true,
        contexts: [],
        checks: [{ context: FIXED.checkName, app_id: appId }]
      } : { message: "Branch not protected" }), { status: protectionStatus });
    }
    throw new Error(`Unexpected GitHub URL: ${url}`);
  };
  return { fetchImpl, calls };
}

function submissionReceipt(blockerId, evidenceSha256, overrides = {}) {
  return {
    receipt_id: `receipt-${blockerId}`,
    blocker_id: blockerId,
    candidate_id: FIXED.expectedCandidateId,
    run_id: FIXED.expectedRunId,
    tenant_scope: TENANT_SCOPE,
    evidence_sha256: evidenceSha256,
    verifier_class: blockerId === "github_app_installation"
      ? "github_api_readback"
      : "repository_policy_readback",
    selectors: {
      repo: "attacker/redirected",
      api_base_url: "https://attacker.example"
    },
    ...overrides
  };
}

test("A3 GitHub resolver verifies a tenant-bound custom App without leaking identity", async () => {
  const transport = githubFetch();
  const options = {
    ...FIXED,
    tenantInstallationBinding: tenantInstallationBinding(),
    fetchImpl: transport.fetchImpl
  };
  const evidence = await captureA3GitHubDeploymentEvidence("github_app_installation", options);
  const observation = await observeA3GitHubDeploymentReceipt({
    receipt: submissionReceipt("github_app_installation", evidence.evidence_sha256)
  }, options);

  assert.equal(observation.production_verified, true);
  assert.equal(observation.authoritative_readback_input.verification_status, "verified");
  assert.equal(observation.authoritative_readback_input.reason_code, "all_bindings_verified");
  assert.deepEqual(observation.authoritative_readback_input.claims, {
    tenant_installation_bound: true,
    repository_bound: true,
    check_identity_verified: true
  });
  assert.equal(observation.receipt_binding.evidence_hash_matches, true);
  assert.equal(observation.safety.a2_decision_recomputed, false);
  assert.equal(transport.calls.every((call) => call.url.startsWith("https://api.github.com/repos/acme/refund-agent/")), true);
  assert.doesNotMatch(JSON.stringify(observation), /rt_secret|private-owner|owner@example\.com|authorization/i);
});

test("A3 GitHub resolver rejects github-actions as a tenant custom App", async () => {
  const transport = githubFetch({ appSlug: "github-actions", appId: 15368 });
  const options = {
    ...FIXED,
    tenantInstallationBinding: tenantInstallationBinding(),
    fetchImpl: transport.fetchImpl
  };
  const evidence = await captureA3GitHubDeploymentEvidence("github_app_installation", options);
  const observation = await observeA3GitHubDeploymentReceipt({
    receipt: submissionReceipt("github_app_installation", evidence.evidence_sha256)
  }, options);

  assert.equal(observation.production_verified, false);
  assert.equal(observation.authoritative_readback_input.verification_status, "rejected");
  assert.equal(observation.authoritative_readback_input.reason_code, "policy_not_satisfied");
  assert.equal(observation.authoritative_readback_input.claims.check_identity_verified, false);
  assert.equal(observation.evidence.provider_readbacks.installation.identity_matches, false);
});

test("A3 GitHub resolver verifies required-check policy only with all authority receipts", async () => {
  const transport = githubFetch();
  const options = {
    ...FIXED,
    failingMergeDenialReceipt: failingMergeDenialReceipt(),
    maintainerApprovalReceipt: maintainerApprovalReceipt(),
    fetchImpl: transport.fetchImpl
  };
  const evidence = await captureA3GitHubDeploymentEvidence("required_check_enforcement", options);
  const observation = await observeA3GitHubDeploymentReceipt({
    receipt: submissionReceipt("required_check_enforcement", evidence.evidence_sha256)
  }, options);

  assert.equal(observation.production_verified, true);
  assert.equal(observation.authoritative_readback_input.verification_status, "verified");
  assert.deepEqual(observation.authoritative_readback_input.claims, {
    required_context_enforced: true,
    failing_merge_denied: true,
    maintainer_readback_verified: true
  });
  assert.equal(observation.evidence.authority_receipts.failing_merge_denial.valid, true);
  assert.equal(observation.evidence.authority_receipts.maintainer_approval.valid, true);
});

test("A3 GitHub resolver turns branch-protection 404 and absent receipts into a trusted rejection", async () => {
  const transport = githubFetch({ protectionStatus: 404 });
  const options = { ...FIXED, fetchImpl: transport.fetchImpl };
  const evidence = await captureA3GitHubDeploymentEvidence("required_check_enforcement", options);
  const observation = await observeA3GitHubDeploymentReceipt({
    receipt: submissionReceipt("required_check_enforcement", evidence.evidence_sha256)
  }, options);

  assert.equal(observation.production_verified, false);
  assert.equal(observation.authoritative_readback_input.verification_status, "rejected");
  assert.equal(observation.authoritative_readback_input.reason_code, "policy_not_satisfied");
  assert.deepEqual(observation.authoritative_readback_input.claims, {
    required_context_enforced: false,
    failing_merge_denied: false,
    maintainer_readback_verified: false
  });
  assert.equal(observation.evidence.provider_readbacks.required_check.http_status, 404);
  assert.equal(observation.evidence.provider_readbacks.required_check.enforced, false);
});

test("A3 GitHub resolver rejects a receipt whose submitted evidence hash is stale", async () => {
  const transport = githubFetch();
  const options = {
    ...FIXED,
    failingMergeDenialReceipt: failingMergeDenialReceipt(),
    maintainerApprovalReceipt: maintainerApprovalReceipt(),
    fetchImpl: transport.fetchImpl
  };
  const observation = await observeA3GitHubDeploymentReceipt({
    receipt: submissionReceipt("required_check_enforcement", `sha256:${"0".repeat(64)}`)
  }, options);

  assert.equal(observation.production_verified, false);
  assert.equal(observation.receipt_binding.evidence_hash_matches, false);
  assert.equal(observation.authoritative_readback_input.reason_code, "hash_mismatch");
});

test("A3 GitHub resolver keeps repository targets server-fixed and records observations", async () => {
  const transport = githubFetch();
  const recorded = [];
  const options = {
    ...FIXED,
    failingMergeDenialReceipt: failingMergeDenialReceipt(),
    maintainerApprovalReceipt: maintainerApprovalReceipt(),
    fetchImpl: transport.fetchImpl,
    recordObservation: async (value) => recorded.push(value)
  };
  const evidence = await captureA3GitHubDeploymentEvidence("required_check_enforcement", options);
  const resolver = createA3GitHubDeploymentReceiptResolver(options);
  const readback = await resolver({
    receipt: submissionReceipt("required_check_enforcement", evidence.evidence_sha256, {
      repo: "attacker/redirected",
      branch: "untrusted",
      token: "client_secret"
    })
  });

  assert.equal(readback.verification_status, "verified");
  assert.equal(recorded.length, 1);
  assert.equal(recorded[0].target.repo, FIXED.repo);
  assert.equal(recorded[0].target.branch, FIXED.branch);
  assert.equal(recorded[0].safety.target_from_client, false);
  assert.equal(transport.calls.every((call) => call.url.startsWith("https://api.github.com/repos/acme/refund-agent/")), true);
  assert.doesNotMatch(JSON.stringify(recorded), /client_secret|rt_secret|authorization/i);
});

test("A3 committed live calibration keeps current GitHub blockers rejected and redacted", async () => {
  const [fixture, check, installation, requiredCheck] = await Promise.all([
    "a3_github_deployment_verifier_calibration_20260713.redacted.json",
    "a3_github_check_head_8d82fd4_live_readback.redacted.json",
    "a3_github_repository_installation_live_readback_20260713.redacted.json",
    "a3_github_main_required_check_live_readback_20260713.redacted.json"
  ].map(async (name) => JSON.parse(await readFile(new URL(`../../fixtures/a3/p3/${name}`, import.meta.url), "utf8"))));
  const serialized = JSON.stringify({ fixture, check, installation, requiredCheck });

  assert.equal(fixture.calibration_only, true);
  assert.equal(fixture.provider_readbacks.check.app_slug, "github-actions");
  assert.equal(fixture.provider_readbacks.repository_installation.http_status, 401);
  assert.equal(fixture.provider_readbacks.repository_installation.identity_matches, false);
  assert.equal(fixture.provider_readbacks.required_check.http_status, 404);
  assert.equal(fixture.provider_readbacks.required_check.enforced, false);
  assert.equal(fixture.provider_readbacks.check.readback_id, check.readback_id);
  assert.equal(fixture.provider_readbacks.check.payload_hash, check.payload_hash);
  assert.equal(fixture.provider_readbacks.repository_installation.readback_id, installation.readback_id);
  assert.equal(fixture.provider_readbacks.repository_installation.payload_hash, installation.payload_hash);
  assert.equal(fixture.provider_readbacks.required_check.proof_id, requiredCheck.proof_id);
  assert.equal(fixture.provider_readbacks.required_check.payload_hash, requiredCheck.payload_hash);
  assert.equal(fixture.verifier_projection.github_app_installation.verification_status, "rejected");
  assert.equal(fixture.verifier_projection.required_check_enforcement.verification_status, "rejected");
  assert.equal(fixture.current_product_posture.production_verified_receipts, 0);
  assert.equal(fixture.current_product_posture.production_ready, false);
  assert.equal(fixture.safety.mutation_performed, false);
  assert.doesNotMatch(serialized, /gh[pousr]_|github_pat_|Bearer |Authorization|Cookie|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|C:\\Users|D:\\/i);
});
