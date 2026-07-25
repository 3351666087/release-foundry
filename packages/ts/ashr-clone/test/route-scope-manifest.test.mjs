import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import {
  consumeOfficialApiMutatingCalibrationIndex,
  consumeGoRouteScopeManifest,
  hostedRouteScopeManifest,
} from "../dist/saas.js";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..", "..", "..");
const snapshotPath = join(repoRoot, "docs", "a1", "evidence", "go_python_ts_route_parity_snapshot.json");
const mutatingIndexPath = join(repoRoot, "docs", "a1", "evidence", "official_api_mutating_calibration_index.json");

function intersection(left, right) {
  return new Set([...left].filter((item) => right.has(item)));
}

function difference(left, right) {
  return new Set([...left].filter((item) => !right.has(item)));
}

function goOpenApiRouteScopeFixture(snapshot) {
  const paths = {};
  for (const route of snapshot.go_manifest_routes) {
    const [method, path] = route.split(" ");
    paths[path] ??= {};
    paths[path][method.toLowerCase()] = { operationId: `fixture_${method.toLowerCase()}_${path}` };
  }
  return {
    schema_version: "ashr.clone.saas_control_plane.v1",
    manifest_schema_version: "ashr.clone.go_route_scope_manifest.v1",
    public_safe: true,
    raw_payloads_included: false,
    source_policy: { private_evidence_read: false, raw_payloads_included: false, tokens_included: false },
    paths,
    route_scope_docs: {
      schema_version: "ashr.clone.go_route_scope_docs.v1",
      public_safe: true,
      raw_payloads_included: false,
      source: "generated_from_go_route_manifest",
      route_groups: [
        {
          name: "usage_quota",
          operations: ["usage", "usage_quota.configure"],
          routes: ["GET /v1/projects/{project_id}/quota", "GET /v1/projects/{project_id}/usage", "POST /v1/projects/{project_id}/quota/limits", "POST /v1/projects/{project_id}/usage/quotas"],
          scopes: ["usage:read"],
        },
        {
          name: "run_lifecycle",
          operations: ["lifecycle"],
          routes: ["GET /v1/projects/{project_id}/runs/{run_id}/lifecycle"],
          scopes: ["run:lifecycle:read"],
        },
        {
          name: "audit",
          operations: ["audit.chain.verify", "audit_log"],
          routes: ["GET /v1/projects/{project_id}/audit-chain/verify", "GET /v1/projects/{project_id}/audit-log", "POST /v1/projects/{project_id}/audit-chain/verify"],
          scopes: ["audit:read"],
        },
      ],
      plan_limits: [
        {
          plan: "Developer",
          cap_mode: "hard_limit",
          public_url: "https://www.ashr.io/pricing",
          limits: [
            { metric: "graded_scenarios", limit: 5000, unit: "scenario" },
            { metric: "observations", limit: 250000, unit: "observation" },
            { metric: "voice_minutes", limit: 1000, unit: "minute" },
            { metric: "projects", limit: 1, unit: "project" },
          ],
        },
        {
          plan: "Startup",
          cap_mode: "overage_billing",
          public_url: "https://www.ashr.io/pricing",
          limits: [
            { metric: "graded_scenarios", limit: 100000, unit: "scenario" },
            { metric: "observations", limit: 10000000, unit: "observation" },
            { metric: "voice_minutes", limit: 50000, unit: "minute" },
            { metric: "projects", limit: 0, unit: "unlimited" },
          ],
        },
      ],
      plan_metrics: [
        { metric: "graded_scenarios", unit: "scenario", operations: ["sdk_submit"], description: "Run submissions counted as graded scenario units." },
        { metric: "observations", unit: "observation", operations: ["ingest_trace"], description: "Trace observation rows accepted by the runtime." },
        { metric: "voice_minutes", unit: "minute", operations: ["upload_run", "ingest_trace"], description: "Voice/media usage documented for quota parity; local runtime records route coverage only." },
        { metric: "projects", unit: "project", operations: ["bootstrap_project"], description: "Project-count limit reference for billing documentation parity." },
      ],
      notes: [
        "plan limits are public documentation references, not secret billing state",
        "route groups are derived from GoRouteManifestEntries",
        "captured HTTP bodies and tenant data are intentionally excluded",
      ],
    },
  };
}

test("TS hosted client consumes Go route/scope manifest public-safely", async () => {
  const snapshot = JSON.parse(await readFile(snapshotPath, "utf8"));
  const manifest = hostedRouteScopeManifest();
  const consumption = consumeGoRouteScopeManifest(snapshotPath);

  assert.equal(manifest.schema_version, "ashr.clone.hosted_route_scope_manifest.v1");
  assert.equal(manifest.public_safe, true);
  assert.equal(consumption.schema_version, "ashr.clone.go_route_scope_consumption.v1");
  assert.equal(consumption.public_safe, true);
  assert.deepEqual(consumption.source_policy, snapshot.source_policy);

  const manifestRoutes = new Set(manifest.routes.map((entry) => entry.route));
  const goRoutes = new Set(snapshot.go_manifest_routes);
  assert.deepEqual(new Set(consumption.consumable_go_routes), intersection(goRoutes, manifestRoutes));
  assert.deepEqual(new Set(consumption.unsupported_go_routes), difference(goRoutes, manifestRoutes));
  assert.deepEqual(new Set(consumption.unsupported_go_route_gaps.map((entry) => entry.route)), new Set(consumption.unsupported_go_routes));
  assert.equal(consumption.unsupported_go_route_gaps.every((entry) => entry.reason && entry.consumer_action), true);
  assert.deepEqual(new Set(consumption.client_only_routes), difference(manifestRoutes, goRoutes));

  const routeScopes = new Map(consumption.route_scopes.map((entry) => [entry.route, entry.required_scopes]));
  assert.deepEqual(routeScopes.get("POST /v1/projects/{project_id}/sdk-submit"), ["sdk:submit"]);
  assert.deepEqual(routeScopes.get("POST /v1/projects/{project_id}/worker-jobs/lease"), ["worker_job:write"]);
  assert.deepEqual(routeScopes.get("GET /v1/projects/{project_id}/worker-jobs"), ["worker_job:read"]);
  assert.deepEqual(routeScopes.get("GET /v1/projects/{project_id}/runs/{run_id}/release-evidence"), ["evidence:read"]);
  assert.equal(consumption.unsupported_go_routes.includes("POST /v1/projects/{project_id}/runs/submit"), true);
  assert.equal(consumption.unsupported_go_routes.includes("GET /v1/identity/oauth/github/start"), true);
  assert.equal(consumption.unsupported_go_routes.includes("GET /v1/identity/oauth/github/callback"), true);
  assert.equal(consumption.unsupported_go_routes.includes("GET /v1/identity/oauth/google/start"), true);
  assert.equal(consumption.unsupported_go_routes.includes("GET /v1/identity/oauth/google/callback"), true);
  for (const route of [
    "POST /v1/accounts/{account_id}/two-factor/disable",
    "POST /v1/accounts/{account_id}/two-factor/recovery-codes/consume",
    "POST /v1/accounts/{account_id}/two-factor/recovery-codes/rotate",
  ]) {
    const gap = consumption.unsupported_go_route_gaps.find((entry) => entry.route === route);
    assert.equal(consumption.unsupported_go_routes.includes(route), true);
    assert.equal(typeof gap?.reason, "string");
    assert.match(gap?.consumer_action ?? "", /UnifiedIdentityHttpClient/);
    assert.equal(Object.hasOwn(gap ?? {}, "replacement_route"), false);
  }
  for (const route of [
    "GET /v1/identity/oauth/github/start",
    "GET /v1/identity/oauth/github/callback",
    "GET /v1/identity/oauth/google/start",
    "GET /v1/identity/oauth/google/callback",
  ]) {
    const gap = consumption.unsupported_go_route_gaps.find((entry) => entry.route === route);
    assert.equal(typeof gap?.reason, "string");
    assert.equal(typeof gap?.consumer_action, "string");
    assert.equal(Object.hasOwn(gap ?? {}, "replacement_route"), false);
  }
  assert.equal(consumption.route_scope_docs, null);
});

test("TS hosted client consumes Go OpenAPI route_scope_docs", async () => {
  const snapshot = JSON.parse(await readFile(snapshotPath, "utf8"));
  const openapi = goOpenApiRouteScopeFixture(snapshot);
  delete openapi.source_policy;
  const consumption = consumeGoRouteScopeManifest(openapi);

  assert.equal(consumption.consumable_go_routes.includes("GET /v1/projects/{project_id}/usage"), true);
  assert.equal(consumption.consumable_go_routes.includes("POST /v1/projects/{project_id}/usage/quotas"), true);
  assert.equal(consumption.consumable_go_routes.includes("GET /v1/projects/{project_id}/runs/{run_id}/lifecycle"), true);
  assert.equal(consumption.route_scope_docs.schema_version, "ashr.clone.go_route_scope_docs.v1");
  assert.deepEqual(consumption.route_scope_docs.route_families, ["audit", "run_lifecycle", "usage_quota"]);
  assert.deepEqual(consumption.route_scope_docs.plan_limits, ["Developer", "Startup"]);
  assert.equal(new Set(consumption.route_scope_docs.plan_metrics).has("voice_minutes"), true);
});

test("TS hosted client consumes future route artifact wrapper", async () => {
  const snapshot = JSON.parse(await readFile(snapshotPath, "utf8"));
  const openapi = goOpenApiRouteScopeFixture(snapshot);
  const wrapped = {
    schema_version: "ashr.clone.route_artifact.worker.v1",
    public_safe: true,
    source_policy: openapi.source_policy,
    paths: openapi.paths,
    artifact: { route_scope_docs: openapi.route_scope_docs },
  };

  const consumption = consumeGoRouteScopeManifest(wrapped);
  assert.deepEqual(consumption.route_scope_docs.route_families, ["audit", "run_lifecycle", "usage_quota"]);
});

test("TS Go OpenAPI route_scope_docs rejects route family drift", async () => {
  const snapshot = JSON.parse(await readFile(snapshotPath, "utf8"));
  const openapi = goOpenApiRouteScopeFixture(snapshot);
  openapi.route_scope_docs.route_groups = openapi.route_scope_docs.route_groups.filter((group) => group.name !== "usage_quota");

  assert.throws(
    () => consumeGoRouteScopeManifest(openapi),
    /missing route families: usage_quota/,
  );
});

test("TS hosted route scope manifest covers every shared TS/Python route", async () => {
  const snapshot = JSON.parse(await readFile(snapshotPath, "utf8"));
  const manifest = hostedRouteScopeManifest();
  const manifestRoutes = new Set(manifest.routes.map((entry) => entry.route));
  const sharedRoutes = intersection(new Set(snapshot.python_hosted_routes), new Set(snapshot.ts_openapi_routes));

  for (const route of sharedRoutes) {
    if (route.startsWith("GET /health") || route.endsWith("openapi.json")) continue;
    assert.equal(manifestRoutes.has(route), true, `missing route scope manifest entry for ${route}`);
  }
});

test("TS Go route consumer rejects missing unsupported gap records", async () => {
  const snapshot = JSON.parse(await readFile(snapshotPath, "utf8"));
  const driftedSnapshot = {
    ...snapshot,
    go_manifest_routes: [...snapshot.go_manifest_routes, "POST /v1/projects/{project_id}/new-go-only-route"],
  };

  assert.throws(
    () => consumeGoRouteScopeManifest(driftedSnapshot),
    /missing=POST \/v1\/projects\/\{project_id\}\/new-go-only-route/,
  );
});

test("TS Go route consumer rejects stale unsupported gap records", async () => {
  const snapshot = JSON.parse(await readFile(snapshotPath, "utf8"));
  const driftedSnapshot = {
    ...snapshot,
    go_manifest_routes: snapshot.go_manifest_routes.filter((route) => route !== "POST /v1/projects/{project_id}/runs/submit"),
  };

  assert.throws(
    () => consumeGoRouteScopeManifest(driftedSnapshot),
    /stale=POST \/v1\/projects\/\{project_id\}\/runs\/submit/,
  );
});

test("TS manifest consumer rejects private manifest paths", () => {
  assert.throws(
    () => consumeGoRouteScopeManifest(join(repoRoot, "docs", "evidence", "private_refs", "route_manifest.json")),
    /private_refs|\.secrets/,
  );
});

test("TS SDK consumes public official API mutating calibration index", () => {
  const consumption = consumeOfficialApiMutatingCalibrationIndex(mutatingIndexPath);

  assert.equal(consumption.schema_version, "ashr.clone.official_api_mutating_calibration_consumption.v1");
  assert.equal(consumption.client, "typescript");
  assert.deepEqual(consumption.modalities, ["text", "image", "audio", "file", "video"]);
  assert.deepEqual(consumption.quota_blocked_modalities, ["text", "image", "audio", "file", "video"]);
  const byModality = new Map(consumption.records.map((record) => [record.modality, record]));
  assert.deepEqual(byModality.get("image").mutating_step_ids, ["create-request-image"]);
  assert.deepEqual(byModality.get("file").observed_error_kinds, ["api"]);
});

test("TS SDK rejects private official API mutating calibration paths", () => {
  assert.throws(
    () => consumeOfficialApiMutatingCalibrationIndex(join(repoRoot, "docs", "evidence", "private_refs", "a1_official_api_mutating_video_20260709_172428.json")),
    /private_refs|\.secrets/,
  );
});
