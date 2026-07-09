import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import { test } from "node:test";

const ROOT = new URL("../../", import.meta.url);
const DOC_PATH = new URL(
  "../../docs/a3/p3_growth_auditor_billing_migration_control_plane_2026_07_09.md",
  import.meta.url
);

const REQUIRED_DIRECTIONS = [
  "PR gate",
  "production replay",
  "enterprise audit",
  "self-host",
  "trace ingestion",
  "judge calibration",
  "incident report",
  "review workflow",
  "billing/usage",
  "API platform"
];

const REQUIRED_ANCHORS = [
  "ANCHOR: A3_GROWTH_AUDITOR_BILLING_MIGRATION_CONTROL_PLANE",
  "ANCHOR: EXISTING_EVIDENCE_ANCHORS",
  "ANCHOR: NEW_SELLABLE_CAPABILITIES",
  "ANCHOR: TOY_MOCKED_READ_ONLY_UPGRADE_LIST",
  "ANCHOR: ACV_RISK_ENTERPRISE_IMPACT",
  "ANCHOR: NEXT_ROUND_20_PLUS_GROWTH_POINTS",
  "ANCHOR: COMMERCIAL_UPGRADE_PRIORITY",
  "ANCHOR: SAFETY_AND_NON_CLAIMS",
  "ANCHOR: ACCEPTANCE"
];

const EVIDENCE_PATHS = [
  "docs/a3/p3_live_ops_control_plane_2026_07_09.md",
  "docs/a3/p3_live_workflow_readiness_2026_07_09.md",
  "docs/a3/p3_billing_migration_readiness_2026_07_09.md",
  "docs/a3/p3_billing_readiness_contract_2026_07_09.md",
  "docs/a3/a3_billing_usage_summary_2026_07_09.md",
  "docs/a3/p3_commercial_api_contract_2026_07_09.md",
  "docs/a3/openapi/a3_commercial_api.openapi.json",
  "docs/a3/p3_pr_gate_workflow_growth_2026_07_07.md",
  "docs/a3/p3_observability_replay_matrix_growth_2026_07_07.md",
  "docs/a3/p3_growth_auditor_round_audit_archive_2026_07_08.md",
  "docs/a3/p3_self_host_console_growth_2026_07_07.md",
  "docs/a1/schemas/trace_event.schema.json",
  "docs/a3/p3_api_calibration_import_error_shapes_2026_07_07.md",
  "docs/a3/p3_incident_replay_queue_growth_2026_07_07.md",
  "docs/a3/p3_review_workflow_durable_storage_2026_07_08.md",
  "tests/a3/a3_live_ops_control_plane.test.mjs",
  "tests/a3/a3_billing_migration_readiness.test.mjs",
  "tests/a3/a3_commercial_api_contract.test.mjs",
  "tests/a3/a3_review_workflow.test.mjs",
  "tests/a3/self_host_console_contract.test.mjs"
];

function countGrowthPointRows(doc) {
  return [...doc.matchAll(/\| G\d{2} \|/g)].length;
}

test("growth auditor billing migration doc covers required commercial directions", async () => {
  const doc = await readFile(DOC_PATH, "utf8");

  assert.equal(doc.length > 12000, true, "doc is too small to be a money-grade audit artifact");

  for (const anchor of REQUIRED_ANCHORS) {
    assert.ok(doc.includes(anchor), `missing required anchor: ${anchor}`);
  }

  for (const direction of REQUIRED_DIRECTIONS) {
    assert.ok(doc.includes(direction), `missing required direction: ${direction}`);
  }

  assert.equal(countGrowthPointRows(doc) >= 20, true, "expected at least 20 next-round growth points");
});

test("growth auditor billing migration doc is bound to existing evidence anchors", async () => {
  const doc = await readFile(DOC_PATH, "utf8");

  for (const relativePath of EVIDENCE_PATHS) {
    assert.ok(doc.includes(relativePath), `doc does not cite evidence path: ${relativePath}`);
    await access(new URL(relativePath, ROOT));
  }
});

test("growth auditor billing migration doc states non-claims and secret safety", async () => {
  const doc = await readFile(DOC_PATH, "utf8");

  for (const term of [
    "No `.env.local` was read.",
    "No live Ashr API was called.",
    "No live GitHub API was called.",
    "No billing provider was called.",
    "No checkout, portal, subscription, invoice",
    "A3 remains a downstream product-console/report/review/audit surface"
  ]) {
    assert.ok(doc.includes(term), `missing safety term: ${term}`);
  }

  assert.doesNotMatch(doc, /Authorization:\s*Bearer/i);
  assert.doesNotMatch(doc, /Cookie:/i);
  assert.doesNotMatch(doc, /ASHR_API_KEY\s*=/i);
  assert.doesNotMatch(doc, /github_pat_|ghp_|AKIA[0-9A-Z]{16}/);
});
