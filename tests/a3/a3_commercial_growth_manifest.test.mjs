import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

import {
  A3_COMMERCIAL_GROWTH_MANIFEST_SCHEMA_VERSION,
  REQUIRED_COMMERCIAL_GROWTH_DIMENSIONS,
  buildA3CommercialGrowthManifest,
  findPotentialSecretLeaks,
  validateA3CommercialGrowthManifest
} from "../../services/report/a3_commercial_growth_manifest.mjs";

const FIXTURE_PATH = new URL("../../fixtures/a3/p3/a3_commercial_growth_manifest.redacted.json", import.meta.url);
const DOC_PATH = new URL("../../docs/a3/p3_commercial_growth_manifest_2026_07_09.md", import.meta.url);
const CHECKLIST_PATH = new URL("../../docs/a3/acceptance_checklist.md", import.meta.url);

async function loadJson(url) {
  return JSON.parse(await readFile(url, "utf8"));
}

test("A3 commercial growth manifest has required dimensions and enough growth points", () => {
  const manifest = buildA3CommercialGrowthManifest();
  const validation = validateA3CommercialGrowthManifest(manifest);

  assert.equal(manifest.schema_version, A3_COMMERCIAL_GROWTH_MANIFEST_SCHEMA_VERSION);
  assert.equal(validation.valid, true, validation.errors.join("\n"));
  assert.equal(manifest.growth_points.length >= 20, true);
  assert.match(manifest.manifest_hash, /^[a-f0-9]{64}$/);

  for (const dimension of REQUIRED_COMMERCIAL_GROWTH_DIMENSIONS) {
    assert.ok(manifest.summary.dimensions[dimension], `missing dimension summary: ${dimension}`);
    assert.equal(manifest.summary.dimensions[dimension].count > 0, true, `dimension has no points: ${dimension}`);
  }

  assert.equal(manifest.summary.points_with_a1_source > 0, true);
  assert.equal(manifest.summary.points_with_a2_source > 0, true);
  assert.equal(manifest.summary.points_with_a3_source > 0, true);
  assert.equal(manifest.summary.points_with_explicit_gaps > 0, true);
});

test("Every commercial growth point binds evidence or an explicit gap", () => {
  const manifest = buildA3CommercialGrowthManifest();

  for (const point of manifest.growth_points) {
    const sourceCount = ["a1", "a2", "a3"].reduce((sum, lane) => (
      sum + point.evidence_bindings[lane].length
    ), 0);
    const gapCount = point.evidence_bindings.gaps.length;
    assert.equal(sourceCount + gapCount > 0, true, `${point.id} has no evidence or gap`);

    const surfaceCount = ["api", "db", "events", "artifacts"].reduce((sum, lane) => (
      sum + point.contract_surface[lane].length
    ), 0);
    assert.equal(surfaceCount > 0, true, `${point.id} has no contract surface`);
    assert.equal(point.evidence_state !== "missing_binding", true, `${point.id} has missing binding state`);
  }
});

test("A3 commercial growth fixture is generated from the current builder and is secret-free", async () => {
  const fixture = await loadJson(FIXTURE_PATH);
  const expected = buildA3CommercialGrowthManifest();

  assert.deepEqual(fixture, expected);
  assert.equal(validateA3CommercialGrowthManifest(fixture).valid, true);
  assert.deepEqual(findPotentialSecretLeaks(fixture), []);

  const serialized = JSON.stringify(fixture);
  assert.doesNotMatch(serialized, /Authorization:\s*Bearer/i);
  assert.doesNotMatch(serialized, /Cookie:/i);
  assert.doesNotMatch(serialized, /RELEASEFOUNDRY_API_KEY\s*=/i);
  assert.doesNotMatch(serialized, /github_pat_|ghp_|AKIA[0-9A-Z]{16}/);
  assert.doesNotMatch(serialized, /C:\\Users\\/i);
});

test("A3 commercial growth docs preserve API DB event artifact and A1/A2 anchors", async () => {
  const doc = await readFile(DOC_PATH, "utf8");
  const requiredAnchors = [
    "ANCHOR: A3_COMMERCIAL_GROWTH_MANIFEST",
    "ANCHOR: GROWTH_POINT_CLASSIFICATION",
    "ANCHOR: API_CONTRACT",
    "ANCHOR: DB_CONTRACT",
    "ANCHOR: EVENT_CONTRACT",
    "ANCHOR: ARTIFACT_CONTRACT",
    "ANCHOR: TENANT_AUTH_RBAC_USAGE_AUDIT",
    "ANCHOR: A1_A2_INTEGRATION",
    "ANCHOR: ACCEPTANCE"
  ];

  for (const anchor of requiredAnchors) {
    assert.ok(doc.includes(anchor), `missing commercial growth doc anchor: ${anchor}`);
  }

  const requiredTerms = [
    "a3.commercial_growth_manifest.v1",
    "GET /api/a3/commercial-growth/manifest",
    "commercial_growth_manifests",
    "commercial_growth.manifest_generated",
    "a3_commercial_growth_manifest.redacted.json",
    "tenant",
    "auth",
    "RBAC",
    "usage",
    "billing",
    "audit",
    "A1 RunResult",
    "A2 GradeResult",
    "does not alter A1 runner or A2 judge semantics"
  ];

  for (const term of requiredTerms) {
    assert.ok(doc.includes(term), `missing commercial growth doc term: ${term}`);
  }
});

test("A3 acceptance checklist records the commercial growth manifest evidence", async () => {
  const checklist = await readFile(CHECKLIST_PATH, "utf8");

  const requiredItems = [
    "A3 Commercial Growth Manifest",
    "services/report/a3_commercial_growth_manifest.mjs",
    "tests/a3/a3_commercial_growth_manifest.test.mjs",
    "fixtures/a3/p3/a3_commercial_growth_manifest.redacted.json",
    "docs/a3/p3_commercial_growth_manifest_2026_07_09.md",
    "20+ growth points"
  ];

  for (const item of requiredItems) {
    assert.ok(checklist.includes(item), `missing acceptance checklist item: ${item}`);
  }
});
