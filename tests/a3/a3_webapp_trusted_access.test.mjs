import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  DashboardApiError,
  fetchDashboard
} from "../../apps/webapp/lib/api.ts";

const webappUrl = new URL("../../apps/webapp/", import.meta.url);

test("dashboard fetch uses same-origin cookies without browser-declared authority", async () => {
  const payload = {
    source: "api-mock",
    source_label: "A1/A2 demo evidence",
    aggregate_scope_status: {
      status: "partial",
      strict_scope_enforced: true,
      excluded_record_count: 2,
      excluded_counts: { auditEvents: 2 },
      reason: "Legacy records were excluded.",
      retry: "Re-ingest with complete scope."
    },
    trusted_release_authority: {
      integrity_verified: true,
      status: "release_ready",
      release_ready: true,
      upstream_decision: "allow",
      reason_code: "none",
      blockers: [],
      decision_ledger: {
        head_hash: "sha256:trusted-head",
        record_id: "sha256:trusted-record"
      }
    },
    summary: { totalRuns: 1, totalCases: 0 },
    run_fixture: {
      runs: [{
        run_id: "run-demo",
        dataset_id: "dataset-demo",
        status: "complete",
        cases: []
      }]
    },
    grade_fixture: { grade_results: [] }
  };
  let requestUrl = "";
  let requestInit;

  await withBrowserFetch(async (input, init) => {
    requestUrl = String(input);
    requestInit = init;
    return Response.json(payload);
  }, async () => {
    const model = await fetchDashboard("api-mock");
    assert.equal(model.source, "api-mock");
    assert.equal(model.runs[0].runId, "run-demo");
    assert.equal(model.aggregateScopeStatus.status, "partial");
    assert.equal(model.aggregateScopeStatus.strictScopeEnforced, true);
    assert.equal(model.aggregateScopeStatus.excludedRecordCount, 2);
    assert.equal(model.trustedReleaseAuthority.integrityVerified, true);
    assert.equal(model.trustedReleaseAuthority.releaseReady, true);
    assert.equal(model.trustedReleaseAuthority.upstreamDecision, "allow");
  });

  const url = new URL(requestUrl);
  assert.equal(url.origin, "https://console.example.test");
  assert.equal(url.pathname, "/api/a3/dashboard");
  assert.equal(url.searchParams.get("source"), "api-mock");
  assert.equal(requestInit.credentials, "include");
  assert.equal(Object.hasOwn(requestInit, "headers"), false);
  assert.doesNotMatch(requestUrl, /(?:x-a3-role|actor|tenant)/i);
});

test("dashboard normalization treats missing scope status and unverified green claims as unsafe", async () => {
  const payload = {
    source: "api-mock",
    trusted_release_authority: {
      integrity_verified: false,
      status: "release_ready",
      release_ready: true,
      upstream_decision: "allow",
      reason_code: "decision_ledger_hash_invalid"
    },
    summary: {},
    run_fixture: { runs: [{ run_id: "run-demo", cases: [] }] },
    grade_fixture: { grade_results: [] }
  };

  await withBrowserFetch(async () => Response.json(payload), async () => {
    const model = await fetchDashboard("api-mock");
    assert.equal(model.aggregateScopeStatus.status, "partial");
    assert.match(model.aggregateScopeStatus.retry, /Re-import records with organization, tenant, workspace, project, and environment scope/);
    assert.equal(model.trustedReleaseAuthority.integrityVerified, false);
    assert.equal(model.trustedReleaseAuthority.releaseReady, false);
    assert.equal(model.trustedReleaseAuthority.status, "integrity_invalid");
    assert.equal(model.trustedReleaseAuthority.upstreamDecision, "unknown");
  });
});

test("dashboard failures preserve status categories without reading or echoing response secrets", async () => {
  const cases = [
    { status: 401, kind: "unauthenticated", retryable: false },
    { status: 403, kind: "denied", retryable: false },
    { status: 404, kind: "not_found", retryable: false },
    { status: 503, kind: "server", retryable: true }
  ];

  for (const expected of cases) {
    let response;
    await withBrowserFetch(async () => {
      response = new Response('{"secret":"Bearer hosted-response-secret"}', { status: expected.status });
      return response;
    }, async () => {
      await assert.rejects(
        fetchDashboard("api-mock"),
        (error) => assertSafeDashboardError(error, expected)
      );
    });
    assert.equal(response.bodyUsed, false, `status ${expected.status} body must remain unread`);
  }

  await withBrowserFetch(async () => {
    throw new Error("Bearer network-secret https://private.example.test/?token=hidden");
  }, async () => {
    await assert.rejects(
      fetchDashboard("api-mock"),
      (error) => assertSafeDashboardError(error, { status: null, kind: "network", retryable: true })
    );
  });
});

test("provider and DataBoundary enforce stale-data clearing and Chinese-first access states", async () => {
  const [apiSource, providerSource, uiSource] = await Promise.all([
    readFile(new URL("lib/api.ts", webappUrl), "utf8"),
    readFile(new URL("components/dashboard-provider.tsx", webappUrl), "utf8"),
    readFile(new URL("components/ui.tsx", webappUrl), "utf8")
  ]);
  const fetchSource = apiSource.slice(
    apiSource.indexOf("export async function fetchDashboard"),
    apiSource.indexOf("export function toDashboardError")
  );
  const deniedSource = uiSource.slice(
    uiSource.indexOf('if (error?.kind === "denied")'),
    uiSource.indexOf('if (error?.kind === "not_found")')
  );
  const partialSource = uiSource.slice(
    uiSource.indexOf('if (model.aggregateScopeStatus.status === "partial")'),
    uiSource.indexOf("return content;")
  );

  assert.match(fetchSource, /credentials:\s*"include"/);
  assert.doesNotMatch(fetchSource, /headers\s*:/);
  assert.match(providerSource, /error: DashboardApiError \| null/);
  assert.match(providerSource, /setModel\(null\)/);
  assert.match(providerSource, /if \(active\) setModel\(nextModel\)/);
  assert.doesNotMatch(providerSource, /reason instanceof Error \? reason\.message/);

  for (const copy of ["请先登录", "无权访问", "未找到证据数据", "证据加载失败", "暂无可验证的证据数据"]) {
    assert.ok(uiSource.includes(copy), `missing Chinese-first boundary copy: ${copy}`);
  }
  assert.match(uiSource, /href="\/login"/);
  assert.match(uiSource, /error\.retryable/);
  assert.match(uiSource, /model\.runs\.length === 0 && model\.cases\.length === 0/);
  assert.match(uiSource, /model\.aggregateScopeStatus\.status === "partial"/);
  assert.ok(
    uiSource.indexOf('if (model.aggregateScopeStatus.status === "partial")')
      < uiSource.indexOf("if (empty) return content"),
    "partial scope warning must render before the empty-state return"
  );
  assert.match(uiSource, /excludedRecordCount/);
  assert.match(uiSource, /onClick=\{reload\}/);
  assert.match(partialSource, /aggregateScopeStatus\.retry/);
  assert.doesNotMatch(partialSource, /onClick=\{reload\}/);
  assert.doesNotMatch(deniedSource, /reload|RefreshCw|href="\/login"/);
});

function assertSafeDashboardError(error, expected) {
  assert.ok(error instanceof DashboardApiError);
  assert.equal(error.kind, expected.kind);
  assert.equal(error.status, expected.status);
  assert.equal(error.retryable, expected.retryable);
  assert.doesNotMatch(
    `${error.name} ${error.message} ${JSON.stringify(error)}`,
    /hosted-response-secret|network-secret|private\.example|Bearer|token=hidden/i
  );
  return true;
}

async function withBrowserFetch(fetchImplementation, operation) {
  const originalWindow = globalThis.window;
  const originalFetch = globalThis.fetch;
  globalThis.window = { location: { origin: "https://console.example.test" } };
  globalThis.fetch = fetchImplementation;
  try {
    return await operation();
  } finally {
    if (originalWindow === undefined) delete globalThis.window;
    else globalThis.window = originalWindow;
    globalThis.fetch = originalFetch;
  }
}
