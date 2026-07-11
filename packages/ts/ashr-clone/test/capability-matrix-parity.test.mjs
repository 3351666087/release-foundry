import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

import {
  CAPABILITY_MATRIX_SCHEMA_VERSION,
  assertCapabilityMatrixSafe,
  buildCapabilityMatrix,
  loadPublicJson,
  validateCapabilityMatrix,
  writeCapabilityMatrix,
} from "../dist/index.js";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(packageRoot, "../../..");

test("TS builds the Python commercial capability matrix from real public indexes", async () => {
  const matrix = await buildCapabilityMatrix({
    publicEvidenceIndexPath: join(repoRoot, "docs/a1/api_calibration/real_api_evidence_index.json"),
    frontendMirrorIndexPath: join(repoRoot, "docs/a1/frontend_mirror/frontend_mirror_index.json"),
    testsRoot: join(repoRoot, "tests/a1"),
  });
  const byName = new Map(matrix.capabilities.map((entry) => [entry.name, entry]));

  assert.equal(matrix.schema_version, CAPABILITY_MATRIX_SCHEMA_VERSION);
  assert.equal(matrix.public_safe, true);
  assert.deepEqual(validateCapabilityMatrix(matrix), []);
  assert.equal(byName.get("list_datasets").real_read_verified, true);
  assert.equal(byName.get("list_datasets").frontend_mirrored, true);
  assert.equal(byName.get("list_datasets").local_runtime, true);
  assert.equal(byName.get("create_request").mutating_planned_or_quota_blocked, true);
  assert.equal(byName.get("dataset_adapter").local_only, true);
  assert.equal(byName.get("trace_fixture").test_covered, true);
  assert.ok(matrix.summary.axis_counts.frontend_mirrored >= 100);
  assert.ok(matrix.summary.axis_counts.real_read_verified >= 5);
  assertCapabilityMatrixSafe(matrix);
});

test("TS capability matrix writes deterministically and refuses private input paths", async () => {
  const temp = mkdtempSync(join(tmpdir(), "ashr-ts-capability-"));
  try {
    const matrix = await buildCapabilityMatrix({
      publicEvidenceIndexPath: join(repoRoot, "docs/a1/api_calibration/real_api_evidence_index.json"),
      frontendMirrorIndexPath: join(repoRoot, "docs/a1/frontend_mirror/frontend_mirror_index.json"),
    });
    const output = await writeCapabilityMatrix(join(temp, "nested/matrix.json"), matrix);
    assert.deepEqual(JSON.parse(readFileSync(output, "utf8")), matrix);
    await assert.rejects(
      loadPublicJson(join(repoRoot, "docs/evidence/private_refs/anything.json")),
      /refusing to load non-public/u,
    );
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

test("TS capability matrix rejects secret-like public artifacts", () => {
  const unsafe = {
    schema_version: CAPABILITY_MATRIX_SCHEMA_VERSION,
    public_safe: true,
    leaked: "Bearer synthetic.not-a-real-token",
    capabilities: [],
  };
  const issues = validateCapabilityMatrix(unsafe);
  assert.equal(issues.some((issue) => issue.kind === "secret_like_value_leaked"), true);
  assert.throws(() => assertCapabilityMatrixSafe(unsafe), /public-safety\/schema issue/u);
});
