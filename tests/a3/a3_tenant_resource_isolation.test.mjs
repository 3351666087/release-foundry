import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import { startA3ApiServer } from "../../services/report/a3_api_server.mjs";
import { A3_RBAC_ROLES } from "../../services/report/a3_auth_rbac_boundary.mjs";
import { createMemoryA3Store } from "../../services/report/a3_store.mjs";

const SCOPE_A = Object.freeze({
  organization_id: "org-a",
  tenant_id: "tenant-a",
  workspace_id: "workspace-a",
  project_id: "project-a",
  environment_id: "production"
});

const SCOPE_B = Object.freeze({
  organization_id: "org-b",
  tenant_id: "tenant-b",
  workspace_id: "workspace-b",
  project_id: "project-b",
  environment_id: "production"
});

test("hosted A3 isolates colliding run, case, and report ids across all five scope levels", async () => {
  const store = createMemoryA3Store({
    sources: {
      "tenant-a-source": snapshot("tenant-a-source", SCOPE_A, "tenant-a-result"),
      "tenant-b-source": snapshot("tenant-b-source", SCOPE_B, "tenant-b-private-result")
    },
    reports: [
      report("tenant-a-source", SCOPE_A, "Tenant A report"),
      report("tenant-b-source", SCOPE_B, "Tenant B private report")
    ]
  });

  await withServer({
    store,
    routeAccessMode: "hosted_enforced",
    resolveTrustedPrincipal: async () => principal(SCOPE_A)
  }, async (url) => {
    const ownRuns = await fetch(`${url}/api/a3/runs?source=tenant-a-source`);
    assert.equal(ownRuns.status, 200);
    assert.deepEqual((await ownRuns.json()).runs.map((item) => item.run_id), ["run-collision"]);

    const ownRun = await fetch(`${url}/api/a3/runs/run-collision?source=tenant-a-source`);
    assert.equal(ownRun.status, 200);
    assert.match(JSON.stringify(await ownRun.json()), /tenant-a-result/);

    const ownCase = await fetch(`${url}/api/a3/cases/case-collision?source=tenant-a-source`);
    assert.equal(ownCase.status, 200);
    assert.match(JSON.stringify(await ownCase.json()), /tenant-a-result/);

    const ownReport = await fetch(`${url}/api/a3/reports/report-collision?source=tenant-a-source`);
    assert.equal(ownReport.status, 200);
    assert.equal((await ownReport.json()).title, "Tenant A report");

    for (const path of [
      "/api/a3/dashboard?source=tenant-b-source",
      "/api/a3/runs?source=tenant-b-source",
      "/api/a3/runs/run-collision?source=tenant-b-source",
      "/api/a3/cases/case-collision?source=tenant-b-source",
      "/api/a3/reports/report-collision?source=tenant-b-source",
      "/api/a3/reports?source=tenant-b-source",
      "/api/a3/runs?source=missing-source"
    ]) {
      const response = await fetch(`${url}${path}`);
      assert.equal(response.status, 404, path);
      const body = await response.json();
      assert.equal(body.schema_version, "a3.api_error.v1");
      assert.equal(body.error, "not_found");
      assert.doesNotMatch(JSON.stringify(body), /tenant-b-private-result|Tenant B private report/);
    }
  });

  const serialized = JSON.stringify(store.exportState().auditEvents);
  assert.doesNotMatch(serialized, /tenant-b-private-result|Tenant B private report/);
});

test("hosted A3 excludes foreign and legacy records from every dashboard aggregate", async () => {
  const source = "aggregate-source";
  const ownScope = scopedRecord(source, SCOPE_A);
  const foreignScope = scopedRecord(source, SCOPE_B);
  const store = createMemoryA3Store({
    sources: {
      [source]: snapshot(source, SCOPE_A, "tenant-a-aggregate-result")
    },
    auditEvents: [
      { ...ownScope, event_id: "audit-own", event_type: "report_view", subject_id: "own-audit" },
      { ...foreignScope, event_id: "audit-foreign", event_type: "report_view", subject_id: "foreign-private-audit" },
      { source, event_id: "audit-legacy", event_type: "report_view", subject_id: "legacy-unscoped-audit" }
    ],
    adminActionRequests: [
      { ...ownScope, request_id: "admin-own", action: "backup", status: "queued" },
      { ...foreignScope, request_id: "admin-foreign-private", action: "restore", status: "queued" }
    ],
    reviewWorkflowRecords: [
      { ...ownScope, record_id: "review-own", record_type: "denial", status: "recorded" },
      { ...foreignScope, record_id: "review-foreign-private", record_type: "approval", status: "recorded" }
    ],
    releaseEvidenceReadbacks: [
      { ...ownScope, readback_id: "readback-own", release_id: "run-collision", resource_kind: "github_check", readback_status: "confirmed" },
      { ...foreignScope, readback_id: "readback-foreign-private", release_id: "run-collision", resource_kind: "github_check", readback_status: "confirmed" }
    ],
    githubPublishReceipts: [
      { ...ownScope, publish_id: "publish-own", release_id: "run-collision", resource_kind: "github_check", status: "accepted" },
      { ...foreignScope, publish_id: "publish-foreign-private", release_id: "run-collision", resource_kind: "github_check", status: "accepted" }
    ],
    idempotencyReceipts: [
      importLedgerEntry("import-own", ownScope),
      importLedgerEntry("import-foreign-private", foreignScope)
    ]
  });

  const dashboard = await store.getDashboardSnapshot(source, {
    enforceScope: true,
    organizationId: SCOPE_A.organization_id,
    tenantId: SCOPE_A.tenant_id,
    workspaceId: SCOPE_A.workspace_id,
    projectId: SCOPE_A.project_id,
    environmentId: SCOPE_A.environment_id
  });
  const serialized = JSON.stringify(dashboard);

  assert.doesNotMatch(serialized, /foreign-private|legacy-unscoped/);
  assert.equal(dashboard.aggregate_scope_status.status, "partial");
  assert.equal(dashboard.aggregate_scope_status.excluded_record_count, 1);
  assert.deepEqual(dashboard.aggregate_scope_status.excluded_counts, {
    auditEvents: 1,
    adminActionRequests: 0,
    reviewWorkflowRecords: 0,
    multimodalReviewAssignmentEvents: 0,
    releaseEvidenceReadbacks: 0,
    githubPublishReceipts: 0,
    deploymentReceipts: 0,
    deploymentReceiptReadbacks: 0,
    importReceipts: 0
  });
  assert.equal(dashboard.aggregate_scope_status.safety.foreign_record_counts_exposed, false);
  assert.equal(dashboard.review_workflow.record_count, 1);
  assert.equal(dashboard.release_evidence_readbacks.readback_count, 1);
  assert.equal(dashboard.github_publish_receipts.receipt_count, 1);
  assert.equal(meterQuantity(dashboard.usage_ledger, "report_views"), 1);
  assert.equal(meterQuantity(dashboard.usage_ledger, "release_evidence_readbacks"), 1);
  assert.equal(meterQuantity(dashboard.usage_ledger, "api_imports"), 1);
});

test("hosted aggregate status does not disclose fully scoped foreign record counts", async () => {
  const source = "aggregate-count-source";
  const store = createMemoryA3Store({
    sources: { [source]: snapshot(source, SCOPE_A, "tenant-a-result") },
    auditEvents: [
      { ...scopedRecord(source, SCOPE_B), event_id: "foreign-only", event_type: "report_view" }
    ]
  });
  const dashboard = await store.getDashboardSnapshot(source, {
    enforceScope: true,
    organizationId: SCOPE_A.organization_id,
    tenantId: SCOPE_A.tenant_id,
    workspaceId: SCOPE_A.workspace_id,
    projectId: SCOPE_A.project_id,
    environmentId: SCOPE_A.environment_id
  });

  assert.equal(dashboard.aggregate_scope_status.status, "complete");
  assert.equal(dashboard.aggregate_scope_status.excluded_record_count, 0);
  assert.equal(dashboard.aggregate_scope_status.safety.foreign_record_counts_exposed, false);
  assert.equal(meterQuantity(dashboard.usage_ledger, "report_views"), 0);
});

test("same source name preserves independent five-level tenant snapshots", async () => {
  const store = createMemoryA3Store();
  const sharedSource = "api-ingest";
  const runResult = (scope, actual) => ({
    schema_version: "a1.run_result.v1",
    ...scope,
    runs: [{
      run_id: "shared-run-id",
      status: "completed",
      cases: [{
        case_id: "shared-case-id",
        scenario_id: "refund-shared-source",
        status: "passed",
        expected: { final_response: "expected" },
        actual: { final_response: actual },
        trace_events: [{ event_type: "agent_response", content: actual }]
      }]
    }]
  });

  await store.importA1RunResult(runResult(SCOPE_A, "tenant-a-only"), {
    source: sharedSource,
    ...scopeOptions(SCOPE_A),
    enforceScope: true,
    idempotencyKey: "same-client-key"
  });
  await store.importA1RunResult(runResult(SCOPE_B, "tenant-b-only"), {
    source: sharedSource,
    ...scopeOptions(SCOPE_B),
    enforceScope: true,
    idempotencyKey: "same-client-key"
  });

  const [dashboardA, dashboardB, caseA, caseB] = await Promise.all([
    store.getDashboardSnapshot(sharedSource, { ...scopeOptions(SCOPE_A), enforceScope: true }),
    store.getDashboardSnapshot(sharedSource, { ...scopeOptions(SCOPE_B), enforceScope: true }),
    store.getCase("shared-case-id", { source: sharedSource, ...scopeOptions(SCOPE_A), enforceScope: true }),
    store.getCase("shared-case-id", { source: sharedSource, ...scopeOptions(SCOPE_B), enforceScope: true })
  ]);
  assert.equal(dashboardA.summary.totalCases, 1);
  assert.equal(dashboardB.summary.totalCases, 1);
  assert.match(JSON.stringify(caseA), /tenant-a-only/);
  assert.doesNotMatch(JSON.stringify(caseA), /tenant-b-only/);
  assert.match(JSON.stringify(caseB), /tenant-b-only/);
  assert.doesNotMatch(JSON.stringify(caseB), /tenant-a-only/);
  assert.equal(
    Object.values(store.exportState().sources).filter((item) => item.source === sharedSource).length,
    2
  );
});

test("review approval resolves a colliding waiver id only inside the exact source and five-level scope", async () => {
  const [waiverFixture, approvalFixture] = await Promise.all([
    loadJson("../../fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json"),
    loadJson("../../fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json")
  ]);
  const store = createMemoryA3Store({
    sources: {
      "tenant-a-source": snapshot("tenant-a-source", SCOPE_A, "tenant-a-result"),
      "tenant-b-source": snapshot("tenant-b-source", SCOPE_B, "tenant-b-result")
    },
    reviewWorkflowRecords: [
      {
        ...scopedRecord("tenant-a-source", SCOPE_A),
        record_id: "waiver-record-a",
        record_type: "waiver",
        subject: { waiver_id: waiverFixture.waiver_id },
        payload: reviewWaiver(waiverFixture, "release-a", "head-a")
      },
      {
        ...scopedRecord("tenant-b-source", SCOPE_B),
        record_id: "waiver-record-b",
        record_type: "waiver",
        subject: { waiver_id: waiverFixture.waiver_id },
        payload: {
          ...reviewWaiver(waiverFixture, "release-b", "head-b"),
          waiver_id: "foreign-waiver-payload"
        }
      }
    ]
  });
  const waiverB = reviewWaiver(waiverFixture, "release-b", "head-b");
  const approvalA = reviewApproval(approvalFixture, "release-a", "head-a");

  const receipt = await store.submitReviewApproval(approvalA, {
    source: "tenant-a-source",
    ...scopeOptions(SCOPE_A),
    generatedAt: "2026-07-12T08:02:00.000Z",
    releaseVersion: "release-a",
    environment: "production",
    headSha: "head-a",
    waiver: waiverB
  });

  assert.equal(receipt.status, "valid_exception_approval");
  assert.equal(receipt.accepted, true);
  const approvalRecord = store.exportState().reviewWorkflowRecords.find((item) => item.record_type === "approval");
  assert.equal(approvalRecord.source, "tenant-a-source");
  assert.equal(approvalRecord.organization_id, SCOPE_A.organization_id);
  assert.equal(approvalRecord.tenant_id, SCOPE_A.tenant_id);
  assert.equal(approvalRecord.workspace_id, SCOPE_A.workspace_id);
  assert.equal(approvalRecord.project_id, SCOPE_A.project_id);
  assert.equal(approvalRecord.environment_id, SCOPE_A.environment_id);
  assert.doesNotMatch(JSON.stringify(approvalRecord), /release-b|head-b|tenant-b/);
});

test("review approval rejects a foreign-only waiver with the same id", async () => {
  const [waiverFixture, approvalFixture] = await Promise.all([
    loadJson("../../fixtures/a3/p3/a3_waiver_request_blocked_exception.redacted.json"),
    loadJson("../../fixtures/a3/p3/a3_approval_record_blocked_exception.redacted.json")
  ]);
  const store = createMemoryA3Store({
    sources: {
      "tenant-a-source": snapshot("tenant-a-source", SCOPE_A, "tenant-a-result"),
      "tenant-b-source": snapshot("tenant-b-source", SCOPE_B, "tenant-b-result")
    },
    reviewWorkflowRecords: [{
      ...scopedRecord("tenant-b-source", SCOPE_B),
      record_id: "foreign-only-waiver",
      record_type: "waiver",
      subject: { waiver_id: waiverFixture.waiver_id },
      payload: reviewWaiver(waiverFixture, "release-b", "head-b")
    }]
  });

  const receipt = await store.submitReviewApproval(reviewApproval(approvalFixture, "release-a", "head-a"), {
    source: "tenant-a-source",
    ...scopeOptions(SCOPE_A),
    generatedAt: "2026-07-12T08:02:00.000Z",
    releaseVersion: "release-a",
    environment: "production",
    headSha: "head-a"
  });

  assert.equal(receipt.status, "invalid_approval");
  assert.equal(receipt.accepted, false);
  const record = store.exportState().reviewWorkflowRecords.find((item) => item.record_type === "approval");
  assert.ok(record.review.findings.some((item) => item.id === "missing_waiver_evidence"));
  assert.doesNotMatch(JSON.stringify(record), /release-b|head-b|tenant-b/);
});

function snapshot(source, scope, actualText) {
  return {
    source,
    tenant_scope: scope,
    runFixture: {
      schema_version: "a1.run_result.v1",
      runs: [{
        run_id: "run-collision",
        status: "completed",
        cases: [{
          case_id: "case-collision",
          scenario_id: "scenario-refund",
          status: "passed",
          expected: { final_response: "expected" },
          actual: { final_response: actualText },
          trace_events: [{ event_type: "agent_response", content: actualText }]
        }]
      }]
    },
    gradeFixture: {
      schema_version: "a2.grade_results.v1",
      grade_results: [{
        run_id: "run-collision",
        case_id: "case-collision",
        scenario_id: "scenario-refund",
        passed: true,
        score: 1,
        primary_failure_class: null
      }]
    }
  };
}

function report(source, scope, title) {
  return {
    schema_version: "a3.shareable_report.v1",
    report_id: "report-collision",
    source,
    tenant_scope: scope,
    title,
    status: "shareable",
    created_at: "2026-07-12T08:00:00.000Z",
    expires_at: "2099-01-01T00:00:00.000Z",
    share_link: {}
  };
}

function principal(scope) {
  return {
    trusted: true,
    authenticated: true,
    role: "owner",
    actor_hash: "actor_tenant_a_0123456789abcdef",
    session: { state: "active" },
    permissions: [...A3_RBAC_ROLES.owner],
    expires_at: "2099-01-01T00:00:00.000Z",
    tenant_scope: scope
  };
}

function scopedRecord(source, scope) {
  return {
    source,
    ...scope,
    tenant_scope: scope
  };
}

function importLedgerEntry(label, scope) {
  return {
    key: `ledger-${label}`,
    request_type: "a1_run_result_import",
    source: scope.source,
    receipt: {
      schema_version: "a3.a1_run_result_ingest.v1",
      ...scope,
      receipt_id: label
    }
  };
}

function meterQuantity(ledger, meter) {
  return ledger.meters.find((item) => item.meter === meter)?.quantity;
}

function scopeOptions(scope) {
  return {
    organizationId: scope.organization_id,
    tenantId: scope.tenant_id,
    workspaceId: scope.workspace_id,
    projectId: scope.project_id,
    environmentId: scope.environment_id
  };
}

function reviewWaiver(fixture, releaseVersion, headSha) {
  return {
    ...structuredClone(fixture),
    release_version: releaseVersion,
    environment: "production",
    run_id: "run-collision",
    head_sha: headSha,
    expiry_date: "2099-01-01T00:00:00.000Z"
  };
}

function reviewApproval(fixture, releaseVersion, headSha) {
  return {
    ...structuredClone(fixture),
    release_version: releaseVersion,
    environment: "production",
    run_id: "run-collision",
    head_sha: headSha,
    co_signers: [
      ...structuredClone(fixture.co_signers || []),
      {
        role: "Evidence owner",
        name: "Evidence owner",
        identity_source: "unit-test",
        signed_at: "2026-07-12T08:01:00.000Z"
      }
    ]
  };
}

async function loadJson(relativePath) {
  return JSON.parse(await readFile(new URL(relativePath, import.meta.url), "utf8"));
}

async function withServer(options, operation) {
  const { server, url } = await startA3ApiServer(options);
  try {
    return await operation(url);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}
