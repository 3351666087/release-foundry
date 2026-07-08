import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const DOC_PATH = new URL("../../docs/a3/p3_self_host_console_growth_2026_07_07.md", import.meta.url);

test("A3 self-host console contract includes required enterprise sections", async () => {
  const doc = await readFile(DOC_PATH, "utf8");

  const requiredHeadings = [
    "## 2. Enterprise Console Pages",
    "## 4. Required DB Tables",
    "## 5. Environment Variables And Redaction Contract",
    "## 6. Health Checks And Readiness",
    "## 7. Retention And Audit Controls",
    "## 9. A1/A2 Compatibility Expectations"
  ];

  for (const heading of requiredHeadings) {
    assert.match(doc, new RegExp(escapeRegExp(heading)), `missing heading: ${heading}`);
  }
});

test("A3 self-host console contract preserves current API, DB, and safety anchors", async () => {
  const doc = await readFile(DOC_PATH, "utf8");

  const requiredTerms = [
    "a3.saas_db_contract.v1",
    "GET /api/a3/health",
    "GET /api/a3/db-contract",
    "GET /api/a3/admin/console",
    "POST /api/a3/reports/share",
    "organizations",
    "api_keys",
    "shareable_reports",
    "audit_events",
    "usage_ledger",
    "ASHR_A3_DB_URL",
    "ASHR_A3_OIDC_CLIENT_SECRET",
    "[REDACTED_DB_URL]",
    "raw signed URLs",
    "legal hold",
    "A1 `RunResult`",
    "a2.grade_results.v1"
  ];

  for (const term of requiredTerms) {
    assert.ok(doc.includes(term), `missing required contract term: ${term}`);
  }
});

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
