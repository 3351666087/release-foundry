import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const packageRoot = fileURLToPath(new URL("../", import.meta.url));
const packageJson = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));

const privateCommandModules = new Set([
  "account-connections-cli",
  "account-readiness-cli",
  "browser-session-cli",
  "browser-session-openapi.generated",
  "cloud-cli",
  "dataset-adapter-cli",
  "github-oauth-cli",
  "probe",
  "runner-cli",
]);

const runtimeMarkers = {
  "account-connections": "AccountConnectionHttpClient",
  "account-readiness": "build_receipt_template",
  "api-client": "AshrApiClient",
  billing: "BillingLedger",
  "browser-session": "BrowserSessionClient",
  calibrate: "runCalibration",
  "capability-matrix": "buildCapabilityMatrix",
  "china-payments": "buildCnyTradePlan",
  "cloud-queue": "CloudQueueWorker",
  commercial: "buildCommercialControlPlaneKit",
  "dataset-adapter": "datasetSourceToCases",
  "delivery-protocol": "identityDeliveryProtocolContractManifest",
  evidence: "buildPrivateEvidenceIndex",
  "github-oauth": "GitHubOAuthHttpClient",
  oauth: "buildAuthorizationEnvelope",
  "python-parity": "stable_id",
  runner: "AgentAdapter",
  saas: "SaaSIngestionClient",
  "session-lifecycle": "SessionLifecycleClient",
  storage: "LocalFilesystemObjectStorage",
  "stripe-executor": "StripeTestHostedExecutor",
  trace: "TraceRecorder",
  "unified-identity": "UnifiedIdentityHttpClient",
};

test("package exports every reusable SDK source module and excludes command-only entry points", () => {
  const sourceModules = readdirSync(new URL("../src/", import.meta.url))
    .filter((name) => name.endsWith(".ts"))
    .map((name) => name.slice(0, -3))
    .filter((name) => name !== "index" && !privateCommandModules.has(name))
    .sort();

  assert.deepEqual(sourceModules, Object.keys(runtimeMarkers).sort());
  assert.deepEqual(
    Object.keys(packageJson.exports).sort(),
    [".", ...sourceModules.map((name) => `./${name}`)].sort(),
  );
  assert.deepEqual(packageJson.files, ["dist", "examples", "README.md"]);

  for (const name of sourceModules) {
    assert.deepEqual(packageJson.exports[`./${name}`], {
      types: `./dist/${name}.d.ts`,
      import: `./dist/${name}.js`,
    });
  }
});

test("ESM consumers import every public subpath through the built package", async () => {
  const root = await import("@ashr-clone/sdk");
  assert.equal(typeof root.CloudApiService, "function");

  for (const [name, marker] of Object.entries(runtimeMarkers)) {
    const module = await import(`@ashr-clone/sdk/${name}`);
    assert.ok(marker in module, `${name} does not export ${marker}`);
  }
});

test("TypeScript consumers resolve declarations for every public ESM subpath", () => {
  const compiler = fileURLToPath(new URL("../node_modules/typescript/bin/tsc", import.meta.url));
  const fixture = fileURLToPath(new URL("./distribution-exports.types.ts", import.meta.url));
  const result = spawnSync(process.execPath, [
    compiler,
    "--noEmit",
    "--strict",
    "--target", "ES2022",
    "--module", "NodeNext",
    "--moduleResolution", "NodeNext",
    fixture,
  ], {
    cwd: packageRoot,
    encoding: "utf8",
  });

  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
});
