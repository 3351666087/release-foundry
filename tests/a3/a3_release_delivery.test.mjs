import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { test } from "node:test";

import {
  buildDeliveryGoldenPath,
  buildDeploymentAcceptance,
  buildReleaseArtifactManifest,
  describeArtifactFile,
  normalizeA2GradeReport,
  summarizeA1RunEvidence,
  summarizeA2GradeEvidence,
  verifyReleaseArtifactManifest
} from "../../services/report/a3_release_delivery.mjs";
import {
  buildReleaseDeliveryOutputs,
  parseReleaseDeliveryArgs
} from "../../services/report/a3_release_delivery_cli.mjs";
import { parseGitHubObserveArgs } from "../../services/report/a3_github_observe_cli.mjs";
import { buildGateCliPayload } from "../../services/report/a3_gate_cli.mjs";

const ROOT = resolve(import.meta.dirname, "../..");

test("A3 normalizes the authoritative A2 judge-service response without recomputing grades", () => {
  const gradeReport = {
    schema_version: "a2.grade_results.v1",
    report_id: "a2-new-run",
    grade_results: [{ case_id: "case-1", passed: false, score: 20, judge_results: [] }]
  };
  assert.equal(normalizeA2GradeReport({ result: { grade_report: gradeReport } }), gradeReport);
  const summary = summarizeA2GradeEvidence({ result: { grade_report: gradeReport } });
  assert.equal(summary.grade_count, 1);
  assert.equal(summary.failed, 1);
  assert.equal(summary.authoritative_owner, "A2");
  assert.equal(summary.a3_recomputed_score, false);
  assert.equal(summary.a3_recomputed_decision, false);
});

test("deployment acceptance stays blocked when A2, hosted runtime, GitHub App, and branch protection are not ready", async () => {
  const runFixture = {
    schema_version: "releasefoundry.run_result.v1",
    run_id: "run-delivery-unit",
    trace_completeness: 1,
    cases: [{ case_id: "case-1", observations: [{ event_type: "agent_response" }] }]
  };
  const gradeFixture = {
    schema_version: "a2.grade_results.v1",
    report_id: "grade-delivery-unit",
    grade_results: [{ case_id: "case-1", passed: false, score: 20, judge_results: [] }]
  };
  const a2TrustedSpine = await json("fixtures/a2/results/a2_trusted_spine_handoff.json");
  const acceptance = buildDeploymentAcceptance({
    runFixture,
    gradeFixture,
    a2TrustedSpine,
    deploymentProbe: {
      hosted_identity: { verified: false, evidence_class: "contract_only" },
      database: { verified: false, evidence_class: "contract_only" },
      queue_worker: { verified: false, evidence_class: "not_proven" },
      object_storage: { verified: false, evidence_class: "not_proven" },
      deployment_target: { verified: false, evidence_class: "not_proven" },
      upgrade_rollback: { verified: false, evidence_class: "not_proven" },
      github_app: { verified: false, evidence_class: "not_proven" }
    },
    githubCheckReadback: {
      provider: "github",
      resource_kind: "check_run",
      readback_status: "readback_confirmed",
      readback_confirmed: true,
      observed: { html_url: "https://github.example/checks/1" }
    },
    githubRequiredCheckProof: { readback_status: "missing", enforced: false }
  }, {
    releaseVersion: "0.2.0-rc.1",
    generatedAt: "2026-07-12T12:00:00.000Z"
  });

  assert.equal(acceptance.status, "blocked");
  assert.equal(acceptance.production_accepted, false);
  assert.ok(acceptance.blocking_check_ids.includes("a2_release_authority"));
  assert.ok(acceptance.blocking_check_ids.includes("github_app_installation"));
  assert.ok(acceptance.blocking_check_ids.includes("github_actions_artifact_readback"));
  assert.ok(acceptance.blocking_check_ids.includes("required_check_enforcement"));
  assert.equal(acceptance.safety.fixture_claimed_as_production, false);
  assert.equal(acceptance.safety.a2_decision_recomputed, false);
});

test("release artifact manifest hashes files and its verifier detects tampering", async () => {
  const temp = await mkdtemp(join(ROOT, "fixtures/a3/golden-path/tmp-release-artifact-"));
  const artifactPath = join(temp, "run.json");
  try {
    await writeFile(artifactPath, `${JSON.stringify({ schema_version: "releasefoundry.run_result.v1", run_id: "run-unit" })}\n`, "utf8");
    const descriptor = await describeArtifactFile("a1_run_result", artifactPath, {
      workspaceRoot: ROOT,
      role: "runtime_evidence",
      sourceLane: "A1"
    });
    const manifest = buildReleaseArtifactManifest({
      a1RunSummary: {
        source_schema_version: "releasefoundry.run_result.v1",
        run_ids: ["run-unit"]
      },
      a2GradeSummary: { source_schema_version: "a2.grade_results.v1" },
      trustedReleaseAuthority: {
        schema_version: "a3.trusted_release_authority.v1",
        integrity_verified: true,
        allowed: false,
        upstream_decision: "block",
        release_ready: false,
        decision_ledger: { head_hash: "sha256:test", record_id: "record-test" }
      },
      artifacts: [descriptor],
      documentation: ["docs/a3/release.md"]
    }, {
      workspaceRoot: ROOT,
      releaseVersion: "0.2.0-rc.1",
      gitSha: "abc123",
      ciTestedSha: "merge456",
      generatedAt: "2026-07-12T12:00:00.000Z"
    });
    const passed = await verifyReleaseArtifactManifest(manifest, {
      workspaceRoot: ROOT,
      verifiedAt: "2026-07-12T12:00:01.000Z"
    });
    assert.equal(passed.status, "passed");
    assert.equal(manifest.release.candidate_only, true);
    assert.equal(manifest.release.production_release, false);
    assert.equal(manifest.authority.a3_recomputed_decision, false);

    await writeFile(artifactPath, "tampered\n", "utf8");
    const failed = await verifyReleaseArtifactManifest(manifest, { workspaceRoot: ROOT });
    assert.equal(failed.status, "failed");
    assert.ok(failed.findings.some((item) => item.id === "artifact_hash_mismatch"));
  } finally {
    await rm(temp, { recursive: true, force: true });
  }
});

test("release evidence never invents a CI-tested SHA from the candidate SHA", () => {
  const gitSha = "c8420813ed6cb94535bd108b30bd97663b906bdb";
  const runFixture = {
    schema_version: "releasefoundry.run_result.v1",
    run_id: "run-not-yet-tested",
    trace_completeness: 1,
    cases: [{ case_id: "case-1", observations: [{ event_type: "agent_response" }] }]
  };
  const gradeFixture = {
    schema_version: "a2.grade_results.v1",
    report_id: "grade-not-yet-tested",
    grade_results: [{ case_id: "case-1", passed: true, score: 100 }]
  };
  const manifest = buildReleaseArtifactManifest({ runFixture, gradeFixture }, {
    releaseVersion: "0.2.0-rc.2",
    gitSha,
    generatedAt: "2026-07-12T12:34:25.000Z"
  });
  const acceptance = buildDeploymentAcceptance({
    runFixture,
    gradeFixture,
    deploymentProbe: { git_sha_alias: gitSha }
  }, {
    releaseVersion: "0.2.0-rc.2",
    gitSha,
    generatedAt: "2026-07-12T12:34:25.000Z"
  });

  assert.equal(manifest.release.git_sha_alias, gitSha);
  assert.equal(manifest.release.ci_tested_sha_alias, null);
  assert.equal(acceptance.release_identity.git_sha_alias, gitSha);
  assert.equal(acceptance.release_identity.ci_tested_sha_alias, null);
});

test("golden path distinguishes a live github.com readback from a confirmed fixture", () => {
  const runFixture = {
    schema_version: "releasefoundry.run_result.v1",
    run_id: "run-live-readback",
    trace_completeness: 1,
    cases: [{ case_id: "case-1", observations: [{}] }]
  };
  const gradeFixture = {
    schema_version: "a2.grade_results.v1",
    report_id: "grade-live-readback",
    grade_results: [{ case_id: "case-1", passed: true, score: 100 }]
  };
  const authority = {
    schema_version: "a3.trusted_release_authority.v1",
    integrity_verified: true,
    allowed: true,
    upstream_decision: "allow",
    release_ready: true,
    blockers: [],
    decision_ledger: { head_hash: "sha256:head" }
  };
  const liveCheck = {
    provider: "github",
    resource_kind: "check_run",
    readback_id: "check-live",
    readback_status: "readback_confirmed",
    readback_confirmed: true,
    observed: { html_url: "https://github.com/acme/repo/runs/123" },
    calibration: { live_readback: true }
  };
  const fixtureCheck = {
    ...liveCheck,
    readback_id: "check-fixture",
    observed: { html_url: "https://github.example/checks/123" },
    calibration: { live_readback: false }
  };
  const base = {
    runFixture,
    gradeFixture,
    trustedReleaseAuthority: authority,
    deploymentAcceptance: {
      production_accepted: false,
      checks: [{ id: "github_app_installation", status: "blocked" }]
    },
    releaseArtifactManifest: {},
    releaseArtifactVerification: {},
    auditBundleVerification: {},
    auditArchiveVerification: {},
    githubRequiredCheckProof: {}
  };
  const live = buildDeliveryGoldenPath({ ...base, githubCheckReadback: liveCheck });
  const fixture = buildDeliveryGoldenPath({ ...base, githubCheckReadback: fixtureCheck });
  assert.equal(live.stages.find((item) => item.id === "github_check").status, "passed");
  assert.equal(fixture.stages.find((item) => item.id === "github_check").status, "blocked");
});

test("release delivery CLI builds a blocked but verifiable packet from A1/A2 evidence", async () => {
  const temp = await mkdtemp(join(ROOT, "fixtures/a3/golden-path/tmp-delivery-cli-"));
  const output = join(temp, "output");
  try {
    const result = await buildReleaseDeliveryOutputs({
      runs: join(ROOT, "fixtures/a3/mock_run_results.json"),
      grades: join(ROOT, "fixtures/a3/mock_grade_results.json"),
      trustedSpine: join(ROOT, "fixtures/a3/golden-path/a2_trusted_spine_handoff.snapshot.json"),
      auditBundle: join(ROOT, "fixtures/a3/p3/a3_audit_bundle_index_blocked_exception.redacted.json"),
      auditBundleVerification: join(ROOT, "fixtures/a3/p3/a3_audit_bundle_verification_passed.redacted.json"),
      auditArchive: join(ROOT, "fixtures/a3/p3/a3_audit_archive_manifest.redacted.json"),
      auditArchiveVerification: join(ROOT, "fixtures/a3/p3/a3_audit_archive_verification_passed.redacted.json"),
      deploymentProbe: join(ROOT, "fixtures/a3/golden-path/deployment_probe.redacted.json"),
      githubActionsArtifactReadback: join(ROOT, "fixtures/a3/golden-path/github-actions-artifact-live-readback.redacted.json"),
      releaseVersion: "0.2.0-rc.1",
      gitSha: "ad6113e01f5999f99b378e678d4f0a9602e8fdbc",
      ciTestedSha: "e07c5f6e3cb8c44e8d75ea781feeec778bb5ccb8",
      generatedAt: "2026-07-12T12:00:00.000Z",
      verifiedAt: "2026-07-12T12:00:01.000Z",
      outputDir: output,
      workspaceRoot: ROOT,
      documentation: ["docs/strategy/large-saas-a1-a2-a3-full-plan.md"]
    });
    assert.equal(result.releaseArtifactVerification.status, "passed");
    assert.equal(result.releaseArtifactManifest.release.git_sha_alias, "ad6113e01f5999f99b378e678d4f0a9602e8fdbc");
    assert.equal(result.releaseArtifactManifest.release.ci_tested_sha_alias, "e07c5f6e3cb8c44e8d75ea781feeec778bb5ccb8");
    const releaseDocument = result.releaseArtifactManifest.artifact_set.artifacts.find((item) => item.id === "release_document_01");
    assert.equal(releaseDocument.path, "docs/strategy/large-saas-a1-a2-a3-full-plan.md");
    assert.equal(releaseDocument.role, "release_documentation");
    assert.match(releaseDocument.sha256, /^[a-f0-9]{64}$/);
    assert.equal(result.deploymentAcceptance.release_identity.ci_tested_sha_alias, "e07c5f6e3cb8c44e8d75ea781feeec778bb5ccb8");
    assert.equal(result.deploymentAcceptance.checks.find((item) => item.id === "github_actions_artifact_readback").status, "passed");
    assert.equal(result.deploymentAcceptance.status, "blocked");
    assert.equal(result.goldenPath.status, "blocked_by_a2");
    assert.equal(result.goldenPath.safety.a2_decision_recomputed, false);
    const index = JSON.parse(await readFile(join(output, "release-delivery-index.json"), "utf8"));
    assert.equal(index.production_ready, false);
    assert.equal(index.git_sha_alias, "ad6113e01f5999f99b378e678d4f0a9602e8fdbc");
    assert.equal(index.ci_tested_sha_alias, "e07c5f6e3cb8c44e8d75ea781feeec778bb5ccb8");
    const verificationOnly = await buildReleaseDeliveryOutputs({
      verifyManifest: join(output, "release-artifact-manifest.json"),
      outputVerification: join(output, "release-artifact-verification-only.json"),
      workspaceRoot: ROOT,
      verifiedAt: "2026-07-12T12:00:02.000Z"
    });
    assert.equal(verificationOnly.mode, "verify_manifest");
    assert.equal(verificationOnly.releaseArtifactVerification.status, "passed");
  } finally {
    await rm(temp, { recursive: true, force: true });
  }
});

test("delivery and GitHub observer argument parsers keep live tokens in environment variables", () => {
  const delivery = parseReleaseDeliveryArgs([
    "--runs", "run.json",
    "--grades", "grades.json",
    "--release-version", "0.2.0-rc.1",
    "--git-sha", "candidate123",
    "--ci-tested-sha", "merge456",
    "--github-actions-artifact-readback", "artifact.json",
    "--verify-manifest", "manifest.json",
    "--output-verification", "verification.json",
    "--doc", "docs/release.md",
    "--no-fail"
  ]);
  assert.equal(delivery.releaseVersion, "0.2.0-rc.1");
  assert.equal(delivery.gitSha, "candidate123");
  assert.equal(delivery.ciTestedSha, "merge456");
  assert.equal(delivery.githubActionsArtifactReadback, "artifact.json");
  assert.equal(delivery.verifyManifest, "manifest.json");
  assert.equal(delivery.outputVerification, "verification.json");
  assert.deepEqual(delivery.documentation, ["docs/release.md"]);
  assert.equal(delivery.noFail, true);

  const observe = parseGitHubObserveArgs([
    "--repo", "acme/repo",
    "--check-run-id", "123",
    "--expected-app-slug", "releasefoundry-enterprise",
    "--expected-app-id", "12345",
    "--expected-installation-alias", "installation-001",
    "--output-installation", "installation.json",
    "--token-env", "TENANT_GITHUB_TOKEN"
  ]);
  assert.equal(observe.checkRunId, 123);
  assert.equal(observe.expectedAppSlug, "releasefoundry-enterprise");
  assert.equal(observe.expectedAppId, 12345);
  assert.equal(observe.expectedInstallationAlias, "installation-001");
  assert.equal(observe.outputInstallation, "installation.json");
  assert.equal(observe.tokenEnvName, "TENANT_GITHUB_TOKEN");
  assert.equal(Object.hasOwn(observe, "token"), false);
});

test("A1 run summary accepts the merged TypeScript runner contract", () => {
  const summary = summarizeA1RunEvidence({
    schema_version: "releasefoundry.run_result.v1",
    run_id: "run-ts",
    trace_completeness: 1,
    cases: [{
      case_id: "case-ts",
      observations: [{ event_type: "message" }, { event_type: "agent_response", tool_calls: [{ name: "tool" }] }]
    }]
  });
  assert.equal(summary.complete, true);
  assert.equal(summary.run_count, 1);
  assert.equal(summary.case_count, 1);
  assert.equal(summary.observation_count, 2);
  assert.equal(summary.tool_call_count, 1);
});

test("Gate CLI consumes wrapped A2 judge-service output and preserves trusted-spine blocking authority", async () => {
  const temp = await mkdtemp(join(ROOT, "fixtures/a3/golden-path/tmp-a2-wrapper-"));
  const wrapperPath = join(temp, "a2-wrapper.json");
  try {
    const gradeReport = await json("fixtures/a3/mock_grade_results.json");
    await writeFile(wrapperPath, `${JSON.stringify({
      schema_version: "a2.internal_service_response.v1",
      ok: true,
      result: { grade_report: gradeReport }
    }, null, 2)}\n`, "utf8");
    const payload = await buildGateCliPayload({
      runs: join(ROOT, "fixtures/a3/mock_run_results.json"),
      grades: wrapperPath,
      a2TrustedSpine: join(ROOT, "fixtures/a3/golden-path/a2_trusted_spine_handoff.snapshot.json"),
      releaseVersion: "0.2.0-rc.1",
      source: "a2-wrapper-test",
      headSha: "abc123",
      noFail: true,
      generatedAt: "2026-07-12T12:00:00.000Z",
      workspaceRoot: ROOT
    });
    assert.equal(payload.summary.totalCases > 0, true);
    assert.equal(payload.trusted_release_authority.upstream_decision, "block");
    assert.equal(payload.trusted_release_authority.release_ready, false);
    assert.equal(payload.local_quality_gate.decision, "block_release");
    assert.equal(payload.release_gate.decision, "block_release");
    assert.equal(payload.release_gate.pr_gate.blocks_merge, true);
    assert.equal(payload.release_workflow.reviewer_workflow.state, "blocked_by_a2");
    assert.equal(payload.release_workflow.reviewer_workflow.sign_off_risk.can_sign_off, false);
    assert.match(payload.pr_comment_markdown, /Decision: \*\*Block release\*\*/);
    assert.match(payload.pr_comment_markdown, /Authority: \*\*A2 Decision Ledger\*\*/);
    assert.match(payload.pr_comment_markdown, /Candidate SHA: `abc123`/);
    assert.doesNotMatch(payload.pr_comment_markdown, /Merge may proceed/);
    assert.equal(payload.github_check_run.conclusion, "failure");
    assert.equal(payload.process_exit_code, 0);
  } finally {
    await rm(temp, { recursive: true, force: true });
  }
});

async function json(path) {
  return JSON.parse(await readFile(join(ROOT, path), "utf8"));
}
