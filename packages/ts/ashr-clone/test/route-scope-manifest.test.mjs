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
