import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import {
  consumeGoRouteScopeManifest,
  hostedRouteScopeManifest,
} from "../dist/saas.js";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..", "..", "..");
const snapshotPath = join(repoRoot, "docs", "a1", "evidence", "go_python_ts_route_parity_snapshot.json");

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
          operations: ["usage"],
          routes: ["GET /v1/projects/{project_id}/quota", "GET /v1/projects/{project_id}/usage"],
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
        "raw request and response payloads are intentionally excluded",
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
  assert.equal(consumption.route_scope_docs, null);
});

test("TS hosted client consumes Go OpenAPI route_scope_docs", async () => {
  const snapshot = JSON.parse(await readFile(snapshotPath, "utf8"));
  const openapi = goOpenApiRouteScopeFixture(snapshot);
  delete openapi.source_policy;
  const consumption = consumeGoRouteScopeManifest(openapi);

  assert.equal(consumption.consumable_go_routes.includes("GET /v1/projects/{project_id}/usage"), true);
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
